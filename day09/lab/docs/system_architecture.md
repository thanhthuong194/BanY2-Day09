# System Architecture — Lab Day 09

**Nhóm:** AI Engineer Solo  
**Ngày:** 2026-04-14  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker (không dùng LangGraph, implement thuần Python)

**Lý do chọn pattern này (thay vì single agent):**

Day 08 RAG pipeline xử lý tất cả trong một hàm (retrieve → generate), khiến debug khó khi pipeline sai. Supervisor-Worker tách biệt rõ trách nhiệm: Supervisor quyết định route (không gọi LLM), mỗi Worker chỉ làm một việc và test được độc lập. Khi answer sai, trace cho biết ngay lỗi ở routing, retrieval, policy, hay synthesis.

---

## 2. Sơ đồ Pipeline

**Sơ đồ thực tế của hệ thống:**

```
User Request (câu hỏi tiếng Việt)
         │
         ▼
┌──────────────────────────────────────────────┐
│              Supervisor Node                 │
│  - Phân tích task bằng keyword matching      │
│  - Set: supervisor_route, route_reason,      │
│         risk_high, needs_tool                │
└──────────────────┬───────────────────────────┘
                   │
           [route_decision()]
                   │
     ┌─────────────┼──────────────┐
     │             │              │
     ▼             ▼              ▼
Retrieval      Policy Tool    Human Review
Worker         Worker         Node (HITL)
│              │              │
│              ├── MCP         │ (auto-approve
│              │   search_kb   │  trong lab)
│              ├── MCP         │
│              │   get_ticket  │
│              │   _info       │
│              └───────────────┘
│                              │
│   (nếu policy worker chưa    │
│    có chunks → gọi thêm      │
│    retrieval_worker)         │
│                              │
└──────────────┬───────────────┘
               │
               ▼
     ┌────────────────────┐
     │   Synthesis Worker │
     │  - Gọi LLM         │
     │    (GPT-4o-mini     │
     │     hoặc Gemini)   │
     │  - Grounded prompt │
     │  - Citation [src]  │
     │  - Confidence est. │
     └────────────┬───────┘
                  │
                  ▼
           Output + Trace
     (final_answer, sources,
      confidence, latency_ms,
      route_reason, workers_called)
```

**MCP Server (mcp_server.py)** được gọi từ policy_tool_worker như một in-process mock:
```
policy_tool_worker
       │
       ├── dispatch_tool("search_kb", {...})
       │         └── tool_search_kb() → ChromaDB
       │
       └── dispatch_tool("get_ticket_info", {...})
                 └── tool_get_ticket_info() → MOCK_TICKETS dict
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích câu hỏi, quyết định route, detect risk, không gọi LLM |
| **Input** | `task: str` từ user |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword matching: policy_keywords → policy_tool_worker; retrieval_keywords → retrieval_worker; risk_keywords → set risk_high=True; ERR code + risk → human_review |
| **HITL condition** | `risk_high=True` AND (`"err-"` in task OR `"không rõ"` in task) |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Embed câu hỏi, query ChromaDB, trả về top-k chunks có score |
| **Embedding model** | `sentence-transformers/all-MiniLM-L6-v2` (offline, 384-dim) |
| **Top-k** | 3 (cấu hình qua `RETRIEVAL_TOP_K` env hoặc state `retrieval_top_k`) |
| **Stateless?** | Yes — không lưu state giữa các lần gọi |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra policy exceptions (rule-based), gọi MCP tools khi needs_tool=True |
| **MCP tools gọi** | `search_kb` (khi chưa có chunks), `get_ticket_info` (khi task chứa ticket/P1) |
| **Exception cases xử lý** | Flash Sale, Digital Product (license key/subscription), Activated Product, Policy Version v3 (đơn trước 01/02/2026) |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | `gpt-4o-mini` (OpenAI) hoặc `gemini-1.5-flash` (Google), fallback nếu không có API key |
| **Temperature** | 0.1 (low — grounded, ít sáng tạo) |
| **Grounding strategy** | System prompt cấm dùng kiến thức ngoài tài liệu; chỉ dùng chunks từ state |
| **Abstain condition** | Khi chunks rỗng hoặc không liên quan → "Không đủ thông tin trong tài liệu nội bộ" |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query: str`, `top_k: int=3` | `chunks: list`, `sources: list`, `total_found: int` |
| `get_ticket_info` | `ticket_id: str` | ticket metadata (priority, status, assignee, sla_deadline, notifications) |
| `check_access_permission` | `access_level: int`, `requester_role: str`, `is_emergency: bool=False` | `can_grant: bool`, `required_approvers: list`, `emergency_override: bool` |
| `create_ticket` | `priority: str`, `title: str`, `description: str=""` | `ticket_id: str`, `url: str`, `created_at: str` |

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| `task` | str | Câu hỏi đầu vào từ user | supervisor đọc, tất cả workers đọc |
| `supervisor_route` | str | Worker được chọn ("retrieval_worker", "policy_tool_worker", "human_review") | supervisor ghi, graph đọc |
| `route_reason` | str | Lý do routing, dùng để debug | supervisor ghi |
| `risk_high` | bool | True nếu phát hiện risk keyword hoặc mã lỗi lạ | supervisor ghi |
| `needs_tool` | bool | True nếu cần gọi MCP tool | supervisor ghi, policy_tool đọc |
| `hitl_triggered` | bool | True nếu human_review được kích hoạt | human_review node ghi |
| `retrieved_chunks` | list | Evidence từ retrieval, mỗi chunk có text/source/score | retrieval_worker ghi, synthesis đọc |
| `retrieved_sources` | list | Danh sách tên file nguồn | retrieval_worker ghi |
| `policy_result` | dict | Kết quả kiểm tra policy: policy_applies, exceptions_found | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list | Danh sách tool calls: {tool, input, output, timestamp} | policy_tool ghi |
| `final_answer` | str | Câu trả lời cuối với citation | synthesis ghi |
| `confidence` | float | Mức tin cậy 0.0–1.0 (dựa vào chunk scores + exceptions) | synthesis ghi |
| `workers_called` | list | Lịch sử tên workers đã được gọi theo thứ tự | mỗi worker append |
| `history` | list | Log text của từng bước (cho debugging) | mỗi node append |
| `latency_ms` | int | Tổng thời gian xử lý tính bằng ms | graph ghi sau khi hoàn thành |
| `run_id` | str | ID duy nhất mỗi run: "run_YYYYMMDD_HHMMSS" | make_initial_state() ghi |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở retrieval, prompt, hay generation | Dễ hơn — xem trace: supervisor_route → test từng worker độc lập |
| Thêm capability mới | Phải sửa toàn prompt hệ thống | Thêm MCP tool trong `mcp_server.py`, không cần sửa graph |
| Routing visibility | Không có — không biết tại sao trả lời một câu hỏi theo cách đó | Có `route_reason` trong mỗi trace |
| Test độc lập | Không thể tách retrieval ra test riêng | `python workers/retrieval.py` chạy được ngay |
| Chi phí LLM | 1 LLM call mỗi query | 1 LLM call (synthesis), retrieval không dùng LLM |

**Quan sát từ thực tế lab:**

Khi q09 (ERR-403-AUTH) trả về "Không đủ thông tin", nguyên nhân tìm ra ngay qua trace: `hitl_triggered=True`, `retrieved_sources=['sla_p1_2026.txt', 'it_helpdesk_faq.txt']` (không liên quan), `confidence=0.30`. Với Day 08 single agent, sẽ phải đọc toàn bộ pipeline để tìm xem bước nào không tìm được thông tin đúng.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Routing dùng keyword matching đơn giản** — Bị lỗi ở q02 (câu retrieval đơn giản về "hoàn tiền" bị route sang policy_tool_worker không cần thiết). Cải tiến: kết hợp keyword với confidence score của retrieval, hoặc dùng lightweight LLM classifier.
2. **Synthesis không cross-document tốt** — q15 (multi-hop) synthesis trả lời đúng nhưng thiếu chi tiết Level 2 emergency bypass. Cần cải thiện prompt để khai thác tốt hơn khi có chunks từ nhiều nguồn.
3. **Confidence estimation rule-based, không calibrated** — Hiện tại dựa trên average chunk score trừ exception penalty. Không phản ánh đúng quality thực của answer (q13 confidence 0.62 nhưng answer đúng, q12 confidence 0.46 nhưng answer sai về temporal scoping).
