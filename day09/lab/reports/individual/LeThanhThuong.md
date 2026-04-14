# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Lê Thanh Thưởng  
**Vai trò trong nhóm:** Worker Owner (Sprint 2)  
**Ngày nộp:** 2026-04-14  
**Độ dài:** ~630 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`
- Phụ trách: `contracts/worker_contracts.yaml` — điền `actual_implementation` cho 3 workers sau khi implement xong
- Functions tôi implement: `retrieval_worker.run()`, `policy_tool_worker.run()` (gồm `analyze_policy()`, `_call_mcp_tool()`), `synthesis_worker.run()`

Sprint 2 yêu cầu implement 3 workers stateless theo contract đã định nghĩa trong `worker_contracts.yaml`. Mỗi worker nhận `AgentState` dict làm input và trả về state đã update, không lưu state nội bộ. `retrieval_worker` query ChromaDB với cosine similarity, trả về top-k chunks + sources. `policy_tool_worker` chạy `analyze_policy()` rule-based, có thể gọi MCP tools qua `_call_mcp_tool()` khi `needs_tool=True`. `synthesis_worker` gọi LLM với grounded prompt, tính `confidence` dựa trên chunk scores.

**Cách công việc kết nối với thành viên khác:**

Lê Văn Tùng (graph.py) gọi `retrieval_worker.run(state)` hoặc `policy_tool_worker.run(state)` tùy route, sau đó gọi `synthesis_worker.run(state)`. MCP client trong `policy_tool_worker` gọi `dispatch_tool()` từ `mcp_server.py` của Nguyễn Đức Sĩ — nếu MCP server chưa xong, policy worker sẽ fail khi `needs_tool=True`. `worker_io_logs` tôi append vào state là nguồn dữ liệu chính để Đinh Thái Tuấn phân tích trong `eval_trace.py`.

**Bằng chứng:**
- `worker_io_logs` hiện diện trong tất cả 15 traces với đủ 2 workers mỗi trace
- Trace q15 (`run_20260414_165911.json`): `policy_tool_worker` gọi 2 MCP calls (search_kb + get_ticket_info), `mcp_calls: 2` trong worker_io_logs

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Thiết kế `synthesis_worker` tính `confidence` dựa trên **trung bình score của retrieved chunks**, thay vì hard-code hoặc để LLM tự output.

**Các lựa chọn thay thế:**
- Hard-code confidence = 0.7 cho tất cả câu → không phản ánh chất lượng retrieval thực tế.
- Để LLM output confidence trong JSON response → không ổn định, LLM hay overconfident.
- Tính từ chunk scores (cosine similarity từ ChromaDB) → confidence phản ánh trực tiếp chất lượng evidence.

**Lý do chọn chunk-score-based confidence:**

Cosine similarity từ ChromaDB là signal khách quan — nếu chunks retrieved có score thấp (< 0.4), nghĩa là không tìm được evidence tốt và câu trả lời dễ bị thiếu ý hoặc abstain. Tôi dùng `avg(chunk_scores) * 0.85` (discount 15% vì synthesis có thể miss ý dù chunks tốt) làm confidence. Điều này giúp `hitl_triggered` hoạt động đúng: confidence < 0.4 → trigger HITL.

**Trade-off đã chấp nhận:**

Chunk score từ ChromaDB không đo chính xác semantic relevance — chỉ đo cosine distance trong embedding space. Câu q10 (store credit) có top chunk score 0.58 nhưng confidence cuối chỉ 0.40 vì 2 chunks còn lại score thấp (0.39, 0.39). Đây là behavior đúng — context không đủ phong phú nên confidence thấp.

**Bằng chứng từ trace/code:**

```
Trace q08 (run_20260414_165843.json):
Chunks retrieved: score=[0.733, 0.520, 0.499] từ sla_p1_2026.txt
avg_score = 0.584, nhưng chunk đầu chỉ có header "=== Phần 3: Quy trình xử lý sự cố P1 ===" không có nội dung
→ synthesis abstain: "Không đủ thông tin trong tài liệu nội bộ."
→ confidence = 0.30 (đúng — không đủ evidence để trả lời)
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `policy_tool_worker.run()` crash với `KeyError` khi state không có `retrieved_chunks` (câu được route thẳng từ supervisor sang policy worker, chưa qua retrieval).

**Symptom:**

Khi chạy thử pipeline lần đầu với câu "hoàn tiền trong bao nhiêu ngày", pipeline crash với:
```
KeyError: 'retrieved_chunks'
```
vì `analyze_policy()` cố access `state["retrieved_chunks"]` trực tiếp, nhưng key này chỉ được set sau khi `retrieval_worker` chạy.

**Root cause:**

`AgentState` khởi tạo với `retrieved_chunks: []` (empty list), nhưng `analyze_policy()` kiểm tra `if state["retrieved_chunks"]` rồi lập tức access `state["retrieved_chunks"][0]["text"]` mà không kiểm tra length. Khi empty list → `state["retrieved_chunks"][0]` raise `IndexError` (không phải `KeyError` — tôi nhầm symptom ban đầu).

**Cách sửa:**

```python
# Trước:
context_chunks = state["retrieved_chunks"]
if context_chunks:
    first_chunk = context_chunks[0]["text"]  # crash khi empty

# Sau:
context_chunks = state.get("retrieved_chunks", [])
# Nếu không có chunks từ retrieval, gọi MCP search_kb để lấy
if not context_chunks and state.get("needs_tool"):
    mcp_result = self._call_mcp_tool("search_kb", {"query": state["task"], "top_k": 3})
    context_chunks = mcp_result.get("chunks", [])
```

**Bằng chứng trước/sau:**

Sau sửa: tất cả 7 policy_tool_worker traces đều có `mcp_calls >= 1` và không có error trong `worker_io_logs`. Trace q02 (run_20260414_165821.json): `"mcp_calls": 1`, `"error": null`.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Ba workers đều stateless và có thể test độc lập — đúng theo contract. `retrieval_worker` không cần graph chạy, `synthesis_worker` chỉ cần list chunks + task là chạy được. Điều này giúp Đinh Thái Tuấn debug từng worker riêng khi có trace bất thường, không cần chạy toàn bộ pipeline.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

`analyze_policy()` xử lý temporal scoping chưa đủ — q12 (đơn 31/01/2026) trả lời theo policy v4 thay vì v3 vì không extract "ngày đặt đơn" riêng biệt. Logic hiện tại chỉ kiểm tra có keyword "trước 01/02/2026" không, chưa parse ngày từ task string.

**Nhóm phụ thuộc vào tôi ở đâu?**

Sprint 3 (Nguyễn Đức Sĩ) và Sprint 4 (Đinh Thái Tuấn) đều cần workers hoạt động đúng. Nếu `policy_tool_worker` không gọi được `_call_mcp_tool()`, MCP server của Nguyễn Đức Sĩ không có trace nào để validate.

**Phần tôi phụ thuộc vào thành viên khác:**

`_call_mcp_tool()` gọi `dispatch_tool()` từ `mcp_server.py` của Nguyễn Đức Sĩ. Tôi cần MCP server có ít nhất `search_kb` hoạt động trước khi policy worker có thể chạy đúng với `needs_tool=True`.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ fix temporal scoping trong `analyze_policy()` vì trace q12 cho thấy pipeline trả lời theo policy v4 nhưng đơn hàng ngày 31/01/2026 phải áp dụng v3 (cutoff 01/02/2026). Fix cụ thể: thêm regex `r'(\d{1,2}/\d{1,2}/\d{4})'` để extract ngày từ task string, so sánh với cutoff riêng biệt trước khi chọn policy version — thay vì chỉ match string "trước 01/02/2026" như hiện tại.

---

*Lưu file này tại: `reports/individual/LeThanhThuong.md`*
