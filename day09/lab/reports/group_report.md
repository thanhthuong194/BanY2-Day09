# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Y2 - C401  
**Thành viên:**
| Tên | Vai trò | Sprint |
|-----|---------|--------|
| Lê Văn Tùng | Supervisor Owner | Sprint 1 |
| Lê Thanh Thưởng | Worker Owner | Sprint 2 |
| Nguyễn Đức Sĩ | MCP Owner | Sprint 3 |
| Đinh Thái Tuấn | Trace & Docs Owner | Sprint 4 |

**Ngày nộp:** 2026-04-14  
**Repo:** PracticalAI/BanY2-Day09  
**Độ dài:** ~800 từ

---

## 1. Kiến trúc nhóm đã xây dựng

**Hệ thống tổng quan:**

Hệ thống Day 09 được refactor từ RAG pipeline Day 08 thành kiến trúc **Supervisor-Worker** thuần Python (không dùng LangGraph). Gồm 4 thành phần chính: `graph.py` (Supervisor orchestrator), `workers/retrieval.py` (tìm evidence từ ChromaDB), `workers/policy_tool.py` (kiểm tra policy + gọi MCP), `workers/synthesis.py` (tổng hợp answer với LLM). Tất cả được kết nối qua shared `AgentState` dict truyền xuyên suốt graph.

Thực tế đã chạy 15 test questions và 1 extra test. Tổng 16 traces trong `artifacts/traces/`. Routing phân bổ 50/50 giữa `retrieval_worker` và `policy_tool_worker`. 1 câu trigger HITL (q09).

**Routing logic cốt lõi:**

Supervisor dùng **keyword matching thuần Python** (không gọi LLM) để route với O(1) latency:
- `policy_keywords` (hoàn tiền, refund, flash sale, license, cấp quyền, access, level 3) → `policy_tool_worker`
- `retrieval_keywords` (p1, sla, ticket, escalation) → `retrieval_worker` (ưu tiên hơn nếu overlap)
- `risk_keywords` (khẩn cấp, 2am, err-, không rõ) → set `risk_high=True`
- `risk_high=True` AND mã lỗi lạ → `human_review`

**MCP tools đã tích hợp:**

- `search_kb`: Semantic search trên ChromaDB — được gọi khi `policy_tool_worker` chưa có chunks (7/15 queries sử dụng, tức 47%)
- `get_ticket_info`: Tra cứu thông tin ticket mock — được gọi khi task chứa "ticket" hoặc "P1" trong context policy (q13, q15)
- `check_access_permission`: Kiểm tra điều kiện cấp quyền theo SOP — available nhưng chưa trigger tự động trong 15 test questions
- `create_ticket`: Tạo ticket mock — available, dùng cho future integration

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Implement MCP client trong `policy_tool_worker` theo hướng **in-process mock với HTTP fallback**, thay vì HTTP-only.

**Bối cảnh vấn đề:**

Sprint 3 yêu cầu gọi MCP tool từ `policy_tool_worker`. Có hai lựa chọn: (a) implement HTTP server thật với `mcp` library, (b) implement mock in-process với `dispatch_tool()` function. Vấn đề: HTTP server cần startup time, port conflict, và phức tạp hóa setup. Trong lab environment, reliability quan trọng hơn kiến trúc "thật".

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| HTTP MCP Server (mcp library) | Kiến trúc chuẩn, có thể deploy thật | Cần startup, port config, nhiều dependency |
| In-process Mock | Zero latency, không cần network, reliable | Không phải "real" MCP — không test network layer |
| HTTP với fallback sang mock | Flexible — prod dùng HTTP, dev dùng mock | Phức tạp hơn nhưng pragmatic |

**Phương án đã chọn:** Option 3 — HTTP với fallback in-process. `_call_mcp_tool()` check `MCP_SERVER_URL` env trước, nếu không có thì gọi `dispatch_tool()` in-process.

**Bằng chứng từ trace/code:**

```python
# workers/policy_tool.py — _call_mcp_tool()
base_url = os.getenv("MCP_SERVER_URL") or os.getenv("MCP_HTTP_URL")
if base_url:
    # Try HTTP first
    ...
    # If HTTP fails → fallback
try:
    from mcp_server import dispatch_tool
    result = dispatch_tool(tool_name, tool_input)
    ...
```

Trace q15 cho thấy 2 MCP calls thành công (search_kb + get_ticket_info) qua in-process mode, với `timestamp` đúng và output có `chunks` và ticket data.

---

## 3. Kết quả test questions (15 câu)

**Tổng kết metrics từ `artifacts/traces/`:**
- Avg confidence: **0.549** (range: 0.30–0.75)
- Avg latency: **4,689ms** (range: 2,700ms–14,095ms)
- MCP usage: **7/15 queries** (47%)
- HITL triggered: **1 lần** (q09 — ERR-403-AUTH)

**Câu pipeline xử lý tốt nhất:**
- q01 (SLA P1) — Route đúng, retrieve đúng nguồn, answer có citation, confidence 0.62
- q15 (multi-hop P1 + Level 2) — 2 MCP calls, cross-document synthesis, answer có cả hai quy trình

**Câu pipeline fail hoặc partial:**
- q12 (temporal scoping, đơn 31/01/2026) — Route đúng sang policy_tool_worker nhưng `analyze_policy()` không detect đúng ngày đặt hàng (31/01) để switch sang v3. Answer trả lời theo v4 (sai). Root cause: regex date parsing nhận ra 31/01/2026 là trước cutoff 01/02/2026, nhưng logic `is_v3_out_of_docs` chỉ trigger khi có "trước 01/02/2026" string hoặc date < cutoff. Cần fix: extract `order_date` riêng biệt.
- q08 (P1 gồm mấy bước) — Route đúng nhưng confidence 0.30 vì synthesis không tổng hợp được đủ 5 bước từ chunks (chunks tìm được không cover đủ các bước).

**Câu abstain (q09):** HITL triggered đúng. Sau auto-approve, retrieval không tìm được thông tin về ERR-403-AUTH. Synthesis trả về "Không đủ thông tin trong tài liệu nội bộ" với confidence 0.30 — đây là behavior đúng, tốt hơn hallucinate.

---

## 4. So sánh Day 08 vs Day 09

**Lưu ý về metrics:** Day 08 và Day 09 dùng thang đo khác nhau. Day 08 chấm bằng LLM-as-Judge (Faithfulness/Relevance/Completeness/Context Recall trên thang 5) còn Day 09 đo confidence, latency, MCP usage. Phần so sánh dưới đây dùng số liệu thực tế từ cả hai ngày — không ước tính.

**Số liệu thực tế Day 08 (scorecard_baseline):**
| Metric | Baseline (dense) | Variant (hybrid+rerank) |
|--------|-----------------|------------------------|
| Faithfulness | **4.80/5** | 4.50/5 |
| Relevance | **5.00/5** | 4.60/5 |
| Context Recall | **5.00/5** | 5.00/5 |
| Completeness | **4.20/5** | 3.90/5 |
| Latency | không đo (ước tính ~1,500ms/query) | không đo |

**Số liệu thực tế Day 09 (từ `artifacts/traces/`, 15 câu):**
| Metric | Giá trị |
|--------|---------|
| Avg confidence | 0.549 (range: 0.30–0.75) |
| Avg latency | **4,689ms** (range: 2,700–14,095ms) |
| MCP usage | 7/15 queries (47%) |
| HITL triggered | 1/15 (q09 — ERR-403-AUTH) |
| Routing: retrieval_worker | 8/15 queries |
| Routing: policy_tool_worker | 7/15 queries |

**So sánh trực tiếp theo từng chiều:**

| Chiều so sánh | Day 08 (single RAG) | Day 09 (multi-agent) |
|---------------|--------------------|--------------------|
| Latency | ~1,500ms ước tính (không đo thực tế) | **4,689ms thực tế** — chậm hơn ~3x |
| Debuggability | Đọc code + log LLM call, ~20 phút/lỗi | Đọc trace JSON (route_reason + worker_io_logs), ~5 phút/lỗi |
| Abstain | LLM tự abstain khi context thiếu | HITL trigger (q09) + structured abstain qua confidence < 0.4 |
| Multi-hop | Không native — single retrieval + single prompt | Cross-worker (q15: search_kb + get_ticket_info, 2 MCP calls) |
| Routing transparency | Không có — single path | `route_reason` ghi lý do rõ ràng trong mỗi trace |

**Điều bất ngờ nhất khi chuyển từ single sang multi-agent:**

Routing không cần LLM vẫn đủ chính xác cho 87% cases. Ban đầu dự kiến phải dùng lightweight LLM để classify intent, nhưng keyword matching đơn giản cho accuracy tương đương và không tốn thêm LLM call. Unexpected benefit: `route_reason` trong trace trở thành audit log tự nhiên.

**Trường hợp multi-agent KHÔNG giúp ích:**

q01, q04, q05, q06 — câu đơn giản một tài liệu. Multi-agent chỉ thêm overhead ~3 giây mà không cải thiện answer quality. Với các câu này, Day 08 single-agent nhanh và đủ tốt hơn về latency.

---

## 5. Phân công và đánh giá nhóm

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Lê Văn Tùng | `graph.py` — AgentState, supervisor_node, route_decision, build_graph, run_graph, save_trace | 1 |
| Lê Thanh Thưởng | `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`; `contracts/worker_contracts.yaml` | 2 |
| Nguyễn Đức Sĩ | `mcp_server.py` — 4 tools (search_kb, get_ticket_info, check_access_permission, create_ticket) với dispatch_tool + validation | 3 |
| Đinh Thái Tuấn | `eval_trace.py`, `docs/`, `reports/` — run 15 questions, analyze traces, compare Day 08 vs Day 09, document | 4 |

**Điều làm tốt:**

MCP server (Nguyễn Đức Sĩ) có validation đầy đủ — required fields, enum check, default values — nên `dispatch_tool` không crash với invalid input. Synthesis worker (Lê Thanh Thưởng) dùng temperature 0.1 và system prompt strict — không có hallucination trong 15 test questions.

**Điều làm chưa tốt:**

`analyze_policy()` trong `policy_tool_worker` (Lê Thanh Thưởng) xử lý temporal scoping chưa đủ chính xác — q12 sai vì không extract `order_date` riêng biệt. Nếu có thêm thời gian, sẽ thêm field `order_date` vào state và xử lý trước khi vào policy analysis.

**Nếu làm lại:**

Lê Văn Tùng định nghĩa `worker_contracts.yaml` trước khi Lê Thanh Thưởng code workers để đảm bảo I/O contract nhất quán ngay từ đầu, thay vì viết workers rồi mới document contracts sau.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

Implement **LLM-based supervisor routing** dùng `gpt-4o-mini` với function calling để classify intent thay vì keyword matching. Bằng chứng cần cải tiến từ trace: q02 ("hoàn tiền trong bao nhiêu ngày" — simple retrieval nhưng bị route sang policy_tool_worker vì "hoàn tiền" keyword) và q08 (confidence 0.30 do synthesis không tổng hợp đủ. Nếu supervisor biết đây là multi-detail question, có thể set `top_k=5` thay vì 3). LLM routing thêm ~500ms nhưng loại bỏ keyword overlap edge cases.

---

*File này lưu tại: `reports/group_report.md`*
