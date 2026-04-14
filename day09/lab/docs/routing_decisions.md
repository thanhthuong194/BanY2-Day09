# Routing Decisions Log — Lab Day 09

**Nhóm:** AI Engineer Solo  
**Ngày:** 2026-04-14

> **Hướng dẫn:** Ghi lại ít nhất **3 quyết định routing** thực tế từ trace của nhóm.
> Không ghi giả định — phải từ trace thật (`artifacts/traces/`).
> 
> Mỗi entry phải có: task đầu vào → worker được chọn → route_reason → kết quả thực tế.

---

## Routing Decision #1

**Task đầu vào:**
> "SLA xử lý ticket P1 là bao lâu?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `Yêu cầu tra cứu thông tin vận hành/SLA -> retrieval_worker`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): "Ticket P1 có SLA phản hồi ban đầu 15 phút, resolution 4 giờ, escalation tự động sau 10 phút không phản hồi."
- confidence: 0.62
- Correct routing? **Yes**

**Nhận xét:** Routing đúng — từ khóa "P1" và "SLA" khớp với nhóm `retrieval_keywords`. Retrieval worker tìm được chunk chính xác từ `sla_p1_2026.txt` (score 0.64). Synthesis tổng hợp đúng thông tin, có citation `[1]`. Đây là routing case lý tưởng: keyword signal rõ ràng, tài liệu có đủ thông tin, confidence hợp lý (0.62).

---

## Routing Decision #2

**Task đầu vào:**
> "ERR-403-AUTH là lỗi gì và cách xử lý?"

**Worker được chọn:** `human_review` → (sau HITL auto-approve) `retrieval_worker`  
**Route reason (từ trace):** `Mã lỗi lạ + rủi ro cao -> human_review | human approved → retrieval`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `human_review → retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): "Không đủ thông tin trong tài liệu nội bộ."
- confidence: 0.30
- Correct routing? **Yes**

**Nhận xét:** Routing đúng — "ERR-" prefix khớp với risk keyword, supervisor nhận diện mã lỗi lạ và kích hoạt HITL. Trong lab mode, HITL auto-approve và forward sang retrieval. Retrieval trả về chunks không liên quan (sla_p1_2026.txt, it_helpdesk_faq.txt), synthesis worker abstain đúng với "Không đủ thông tin" và confidence 0.30. Đây là trường hợp pipeline behave correctly: thừa nhận giới hạn thay vì hallucinate.

---

## Routing Decision #3

**Task đầu vào:**
> "Sản phẩm kỹ thuật số (license key) có được hoàn tiền không?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `Phát hiện từ khóa chính sách/quyền truy cập -> policy_tool_worker`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** `policy_tool_worker (gọi MCP search_kb) → synthesis_worker`

**Kết quả thực tế:**
- final_answer (ngắn): "Sản phẩm kỹ thuật số (license key) không được hoàn tiền theo chính sách v4 Điều 3."
- confidence: 0.49
- Correct routing? **Yes**

**Nhận xét:** Routing đúng — từ khóa "license" khớp với `policy_keywords`. Policy worker gọi MCP `search_kb` để lấy chunks, sau đó `analyze_policy()` phát hiện `digital_product_exception`. Confidence 0.49 thấp hơn kỳ vọng do retrieval lấy thêm chunk không liên quan từ `it_helpdesk_faq.txt`, gây exception_penalty. Cải tiến: lọc chunks theo relevance score trước khi đưa vào policy analysis.

---

## Routing Decision #4 (tuỳ chọn — bonus)

**Task đầu vào:**
> "Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình."

**Worker được chọn:** `policy_tool_worker`  
**Route reason:** `Phát hiện từ khóa chính sách/quyền truy cập -> policy_tool_worker | Cảnh báo rủi ro cao`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Câu q15 là multi-hop yêu cầu cả hai: SLA P1 notifications (domain: `sla_p1_2026.txt`) VÀ Level 2 emergency access (domain: `access_control_sop.txt`). Supervisor chỉ route sang một worker, nhưng vì `policy_tool_worker` gọi MCP `search_kb` và `get_ticket_info` (2 MCP calls), nó thu thập được chunks từ cả hai nguồn. Synthesis tổng hợp được câu trả lời hợp lý nhưng bỏ sót chi tiết: Level 2 emergency bypass CÓ thể cấp với Line Manager + IT Admin (không cần IT Security), nhưng trace cho thấy synthesis không nêu rõ điểm này. Đây là trường hợp routing đúng worker nhưng synthesis vẫn thiếu một detail quan trọng.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8 | 50% |
| policy_tool_worker | 8 | 50% |
| human_review | 1 (q09, sau đó forward sang retrieval) | 6% |

*(q09 được count vào retrieval_worker vì là điểm dừng cuối)*

### Routing Accuracy

> Trong số 15 câu test đã chạy, supervisor route như thế nào:

- Câu route đúng: **13 / 15**
- Câu route sai hoặc suboptimal:
  - q02 ("hoàn tiền trong bao nhiêu ngày"): route sang `policy_tool_worker` vì từ khóa "hoàn tiền", nhưng đây là câu retrieval đơn giản, không cần policy check
  - q08 ("quy trình P1 gồm mấy bước"): route đúng sang `retrieval_worker` nhưng confidence chỉ 0.30 — synthesis không tổng hợp được đủ 5 bước từ chunks
- Câu trigger HITL: **1** (q09 — ERR-403-AUTH với mã lỗi lạ + risk flag)

### Lesson Learned về Routing

1. **Keyword matching đủ dùng cho 5 categories trong lab** — 87% routing accuracy với O(1) latency (~0ms overhead). Trade-off: edge case như q02 (câu retrieval đơn giản về số ngày nhưng chứa từ "hoàn tiền") bị misroute.
2. **Risk detection cần thêm context** — Hiện tại risk flag chỉ dựa vào từ khóa ("khẩn cấp", "2am", "ERR-"). Sẽ chính xác hơn nếu kết hợp với confidence của retrieval trước đó.

### Route Reason Quality

Nhìn lại các `route_reason` trong trace — chúng đủ để debug ở mức cơ bản (biết worker nào được chọn và tại sao), nhưng thiếu một số thông tin:

- **Thiếu:** keyword nào cụ thể khớp (ví dụ: "khớp từ 'license' trong policy_keywords")
- **Thiếu:** confidence score của retrieval (nếu thấp → có thể cần route khác)
- **Cải tiến đề xuất:** format `route_reason` thành structured string: `"{keyword_matched}→{worker}|risk={risk_level}|confidence_hint={score}"`
