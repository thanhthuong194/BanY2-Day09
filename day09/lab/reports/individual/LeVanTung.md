# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Lê Văn Tùng  
**MSSV:** 2A202600111  
**Vai trò trong nhóm:** Supervisor Owner (Sprint 1)  
**Ngày nộp:** 2026-04-14  
**Độ dài:** ~620 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`
- Functions tôi implement: `supervisor_node()`, `route_decision()`, `build_graph()`, `run_graph()`, `save_trace()`

Sprint 1 yêu cầu xây dựng supervisor orchestrator — bộ não điều phối toàn bộ pipeline. Trong `supervisor_node()`, tôi implement logic keyword matching để phân tích task và quyết định route: câu nào chứa "P1/SLA/ticket/escalation" → `retrieval_worker`; câu nào chứa "hoàn tiền/refund/flash sale/license/cấp quyền/access" → `policy_tool_worker`; câu chứa mã lỗi lạ (ERR-xxx) kèm rủi ro cao → `human_review`. Hàm `route_decision()` trả về `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` theo đúng contract trong `worker_contracts.yaml`.

**Cách công việc kết nối với thành viên khác:**

`graph.py` là entry point — tôi gọi `retrieval_worker.run()` và `policy_tool_worker.run()` do Lê Thanh Thưởng implement, sau đó chuyển state sang `synthesis_worker.run()` để tổng hợp câu trả lời. Đinh Thái Tuấn import `run_graph` và `save_trace` trực tiếp từ `graph.py` để chạy `eval_trace.py`. Nếu `build_graph()` chưa xong, Sprint 4 bị block hoàn toàn.

**Bằng chứng:**
- 15 trace files trong `artifacts/traces/` đều có `supervisor_route` và `route_reason` không rỗng
- Trace `run_20260414_165807.json` (q01): `route_reason = "Yêu cầu tra cứu thông tin vận hành/SLA -> retrieval_worker"`, `latency_ms = 14095`

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Dùng **keyword matching thuần Python** để route, thay vì gọi LLM classifier.

**Các lựa chọn thay thế:**
- Gọi `gpt-4o-mini` với function calling để classify intent → chính xác hơn nhưng thêm ~500–800ms latency và thêm chi phí LLM call.
- Rule-based if/else đơn giản (chỉ 1-2 keyword) → nhanh nhưng dễ miss edge case.
- Keyword matching có ưu tiên (priority order) → nhanh, không tốn LLM, đủ chính xác cho 5 categories.

**Lý do chọn keyword matching có ưu tiên:**

Trong lab context, reliability và tốc độ setup quan trọng hơn accuracy tuyệt đối. Keyword matching chạy O(1), không cần API call, và cho phép trace `route_reason` rõ ràng mà không cần parse LLM output. Tôi thiết kế priority: `retrieval_keywords` ưu tiên hơn `policy_keywords` khi có overlap (ví dụ câu có cả "P1" và "cấp quyền" sẽ vào `retrieval_worker` trước).

**Trade-off đã chấp nhận:**

Keyword matching không hiểu ngữ nghĩa — q02 ("hoàn tiền trong bao nhiêu ngày") bị route sang `policy_tool_worker` vì trigger "hoàn tiền" keyword, dù thực chất là câu retrieval đơn giản. Kết quả vẫn đúng (confidence 0.56) nhưng tốn thêm 1 MCP call không cần thiết.

**Bằng chứng từ trace/code:**

```
Trace q02 (run_20260414_165821.json):
"route_reason": "Phát hiện từ khóa chính sách/quyền truy cập -> policy_tool_worker"
"mcp_tools_used": [{"tool": "search_kb", ...}]
"confidence": 0.56
"latency_ms": 4281
```

So sánh với q01 (retrieval_worker, không cần MCP): latency 14,095ms do API call chậm, nhưng không có overhead MCP dispatch. Route đúng loại câu hỏi.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `save_trace()` ghi file JSON với `ensure_ascii=True` mặc định → tên tiếng Việt trong `route_reason` bị encode thành `\uXXXX`, không đọc được bằng text editor.

**Symptom:**

Khi Đinh Thái Tuấn mở trace file để analyze, `route_reason` xuất hiện dạng: `"Ph\u00e1t hi\u1ec7n t\u1eeb kh\u00f3a..."` thay vì tiếng Việt đọc được. Gây khó khăn khi debug routing decision thủ công.

**Root cause:**

`json.dump(..., ensure_ascii=True)` là default của Python — encode tất cả non-ASCII character. Trong `save_trace()`, tôi quên truyền `ensure_ascii=False`.

**Cách sửa:**

```python
# Trước:
json.dump(state, f, indent=2)

# Sau:
json.dump(state, f, indent=2, ensure_ascii=False)
```

**Bằng chứng trước/sau:**

Tất cả 15 trace files trong `artifacts/traces/` hiển thị tiếng Việt đúng (ví dụ: `"route_reason": "Yêu cầu tra cứu thông tin vận hành/SLA -> retrieval_worker"`). Không có chuỗi `\uXXXX` trong bất kỳ trace nào.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

`route_reason` trong mọi trace đều rõ ràng, không có trace nào để "unknown" hay rỗng — đúng với ràng buộc trong `worker_contracts.yaml`. Điều này giúp Đinh Thái Tuấn viết `routing_decisions.md` nhanh vì có evidence cụ thể trong từng trace, không cần suy luận.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Keyword list thiếu một số alias (ví dụ "refund" tiếng Anh không trigger nếu câu hỏi dùng tiếng Anh hoàn toàn). Ngoài ra, priority rule "retrieval ưu tiên hơn policy khi overlap" chưa được test đầy đủ — chỉ dựa vào 15 test questions nên có thể bị miss edge case.

**Nhóm phụ thuộc vào tôi ở đâu?**

`graph.py` là dependency của Sprint 2, 3, 4. Nếu `build_graph()` hoặc `run_graph()` chưa chạy được, toàn bộ team bị block. Thực tế Sprint 1 hoàn thành trước khi Sprint 2–4 bắt đầu nên không có blocking.

**Phần tôi phụ thuộc vào thành viên khác:**

Tôi cần Lê Thanh Thưởng hoàn thành interface của `retrieval_worker.run()` và `policy_tool_worker.run()` để `supervisor_node` có thể dispatch đúng. Tôi dùng mock function ban đầu và thay thế khi workers sẵn sàng.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **LLM-based fallback routing** cho các câu không match keyword rõ ràng — vì trace q02 cho thấy câu "hoàn tiền trong bao nhiêu ngày" bị route sai loại (policy thay vì retrieval) dẫn đến 1 MCP call thừa. Thay vì gọi LLM cho tất cả câu, tôi chỉ gọi khi confidence của keyword matching thấp (ví dụ: chỉ match 1 keyword mờ, không match keyword ưu tiên). Ước tính: thêm ~500ms chỉ cho ~20% câu — trade-off chấp nhận được so với routing accuracy cải thiện.

---

*Lưu file này tại: `reports/individual/LeVanTung.md`*
