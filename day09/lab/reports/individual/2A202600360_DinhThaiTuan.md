# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Đinh Thái Tuấn 2A202600360 
**Vai trò trong nhóm:** Trace & Docs Owner (kiêm Supervisor Owner + Worker Owner + MCP Owner)  
**Ngày nộp:** 2026-04-14  
**Độ dài:** ~650 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `eval_trace.py` (Sprint 4 — run pipeline, analyze traces, compare)
- Functions tôi implement: `run_test_questions()`, `run_grading_questions()`, `analyze_traces()`, `compare_single_vs_multi()`, `save_eval_report()`, `print_metrics()`
- Thực hiện full run 15 test questions → 15 trace files trong `artifacts/traces/`
- Điền 3 docs templates: `docs/routing_decisions.md`, `docs/system_architecture.md`, `docs/single_vs_multi_comparison.md`

**Cách công việc của tôi kết nối với phần của thành viên khác:**

`eval_trace.py` import trực tiếp từ `graph.py` (`run_graph`, `save_trace`). Nếu `graph.py` chưa hoàn chỉnh, tôi không thể chạy được. Tương tự, trace files chứa output của cả 3 workers — nên accuracy của docs tôi viết phụ thuộc vào quality của retrieval, policy, và synthesis workers.

**Bằng chứng:**
- 16 trace files trong `artifacts/traces/` (run_20260414_165807.json đến run_20260414_165911.json)
- `artifacts/eval_report.json` — báo cáo tổng kết comparison Day 08 vs Day 09
- `docs/routing_decisions.md`, `docs/system_architecture.md`, `docs/single_vs_multi_comparison.md` — 3 templates điền xong

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Dùng **in-process dispatch với HTTP fallback** cho MCP client trong `policy_tool_worker`, thay vì require HTTP server.

**Lý do:**

Khi implement Sprint 4 và chạy `eval_trace.py` lần đầu, tôi nhận ra rằng nếu MCP client require HTTP server mới chạy được, thì `eval_trace.py` sẽ fail với `ConnectionRefusedError` trước khi chạy được câu nào. Lab environment không có running HTTP MCP server. Quyết định: `_call_mcp_tool()` check `MCP_SERVER_URL` env var trước, nếu không có thì import và call `dispatch_tool()` trực tiếp từ `mcp_server.py`.

**Trade-off đã chấp nhận:**

Mock in-process không test HTTP layer. Nếu deploy production với real MCP server, cần test lại phần HTTP. Nhưng trong context lab với 60 phút mỗi sprint, reliability > purity.

**Bằng chứng từ trace/code:**

```python
# workers/policy_tool.py — _call_mcp_tool()
base_url = os.getenv("MCP_SERVER_URL") or os.getenv("MCP_HTTP_URL")
if base_url:
    # Try HTTP POST to /tools/call
    ...
    # If HTTP fails → fall through to mock

# Fallback: in-process dispatch
from mcp_server import dispatch_tool
result = dispatch_tool(tool_name, tool_input)
```

Trace q13 (artifacts/traces/run_20260414_165857.json):
```json
"mcp_tools_used": [
  {"tool": "search_kb", "timestamp": "2026-04-14T16:58:53"},
  {"tool": "get_ticket_info", "timestamp": "2026-04-14T16:58:55"}
]
```
Cả 2 MCP calls thành công qua in-process mock, không cần HTTP server.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `analyze_traces()` đếm sai MCP usage rate vì `retrieved_sources` có thể là empty list ngay cả khi trace có sources trong field khác.

**Symptom:**

Khi chạy `eval_trace.py --analyze` lần đầu, `source_coverage` trả về rất ít sources dù traces có nhiều retrieved_chunks. Nhìn vào trace files, field `retrieved_sources` đôi khi là `[]` (empty) trong khi `sources` (từ synthesis) có đủ dữ liệu. Ví dụ: q15 có `"retrieved_sources": []` nhưng `"sources": ["access_control_sop.txt", "sla_p1_2026.txt"]`.

**Root cause:**

Trong `graph.py`, khi `policy_tool_worker` chạy trước `retrieval_worker`, chunks được lấy qua MCP `search_kb` nhưng `retrieved_sources` không được update (chỉ được set trong `retrieval_worker.run()`). `policy_tool_worker` set `retrieved_chunks` nhưng không set `retrieved_sources`.

**Cách sửa:**

Trong `analyze_traces()`, dùng `t.get("retrieved_sources", []) or t.get("sources", [])` — fallback sang field `sources` (từ synthesis) nếu `retrieved_sources` empty:

```python
for src in t.get("retrieved_sources", []) or t.get("sources", []):
    source_counts[src] = source_counts.get(src, 0) + 1
```

**Bằng chứng trước/sau:**

Trước sửa: `source_coverage` chỉ có 8 entries (chỉ từ retrieval_worker traces).  
Sau sửa: `top_sources = [('sla_p1_2026.txt', 7), ('policy_refund_v4.txt', 4), ('access_control_sop.txt', 4), ('it_helpdesk_faq.txt', 3), ('hr_leave_policy.txt', 2)]` — đủ 5 nguồn, phản ánh đúng toàn bộ 16 traces.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Phân tích trace thực tế và documentation. Thay vì ghi templates chung chung, tôi đọc từng trace file, extract số liệu thực (avg confidence 0.549, avg latency 4,689ms, MCP usage 47%), và dùng ví dụ cụ thể (q09 HITL, q12 temporal scoping failure) để điền vào docs. Documentation phản ánh thực trạng pipeline, không phải lý thuyết.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Chưa implement `compare_single_vs_multi()` với real Day 08 data — phải dùng ước tính cho Day 08 baseline. Nếu có Day 08 `eval.py` output thật, comparison sẽ chính xác hơn. Metrics như "multi-hop accuracy 40% vs 60%" là ước tính, không phải đo thực tế.

**Nhóm phụ thuộc vào tôi ở đâu?**

Sprint 4 là sprint cuối — nếu tôi không chạy được `eval_trace.py`, không có trace files, không có docs điền xong, nhóm không có deliverable hoàn chỉnh. Tôi là bottleneck của phần documentation và evidence.

**Phần tôi phụ thuộc vào thành viên khác:**

`eval_trace.py` import `run_graph` và `save_trace` từ `graph.py`. Nếu Supervisor Owner chưa implement `build_graph()` đúng cách, tôi không chạy được. Thực tế: `graph.py` đã hoàn chỉnh từ Sprint 1, nên Sprint 4 chạy suôn sẻ.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ fix lỗi temporal scoping trong `analyze_policy()` vì trace q12 cho thấy: đơn đặt ngày 31/01/2026 (trước cutoff 01/02/2026) nhưng pipeline trả lời theo policy v4 (sai — phải dùng v3). Root cause: `_parse_mentioned_dates()` parse được `31/01/2026` và nhận ra `31/01/2026 < cutoff`, nhưng `is_v3_out_of_docs` logic không distinguish được đây là *ngày đặt hàng* hay *ngày yêu cầu hoàn tiền*. Fix: thêm regex riêng để extract "ngày đặt đơn" vs "ngày yêu cầu", rồi chỉ check ngày đặt đơn với cutoff.

---

*Lưu file này tại: `reports/individual/ai_engineer.md`*
