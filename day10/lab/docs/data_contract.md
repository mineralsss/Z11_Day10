# Data contract — Lab Day 10

> Bắt đầu từ `contracts/data_contract.yaml` — mở rộng và đồng bộ file này.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `data/docs/policy_refund_v4.txt` | Batch file scan (text) | Stale content (còn refund 14 ngày), parse lỗi ký tự | `no_stale_refund_window` (halt), freshness SLA 24h, alert `teams://z11-day10-data-alerts` |
| `data/docs/sla_p1_2026.txt` | Batch file scan (text) | Thiếu/đổi format thời gian SLA, nhầm version | Freshness theo `exported_at`, so sánh `doc_id` trong allowlist |
| `data/docs/it_helpdesk_faq.txt` | Batch file scan (text) | Trùng chunk FAQ hoặc chunk quá ngắn | `no_duplicate_chunk_text` (warn), `chunk_text.min_length >= 8` |
| `data/docs/hr_leave_policy.txt` | Batch file scan (text) | Lẫn bản cũ trước cutoff, xung đột chính sách ngày phép | Quarantine theo cutoff `hr_leave_min_effective_date=2026-01-01`, monitor `quarantine_records` |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | ID ổn định sau clean (hash hoặc `doc_id + seq`), dùng làm khóa upsert embed |
| doc_id | string | Có | Khóa logic nguồn; phải thuộc allowlist: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy` |
| chunk_text | string | Có | Nội dung chunk đã chuẩn hóa; ràng buộc độ dài tối thiểu `8` ký tự |
| effective_date | date | Có | Ngày hiệu lực chuẩn ISO; dùng để loại bản policy cũ và truy vết version |
| exported_at | datetime | Có | Timestamp export phục vụ freshness check ở boundary `ingest` và `publish` |

Quy ước schema fail:
- Thiếu trường bắt buộc hoặc parse ngày thất bại: đưa vào quarantine.
- Không cố “đoán” dữ liệu để pass expectation ở pipeline chuẩn.

---

## 3. Quy tắc quarantine vs drop

Luồng xử lý record lỗi:
- Record lỗi recoverable (sai format ngày, ngoài allowlist, cũ hơn cutoff policy): chuyển vào `artifacts/quarantine/quarantine_<run_id>.csv`.
- Record vi phạm nghiêm trọng policy refund stale (14 ngày thay vì 7 ngày): expectation `no_stale_refund_window` ở mức `halt`, dừng publish nếu không bật chế độ demo inject.
- Record trùng `chunk_text`: cảnh báo `warn`; có thể vẫn publish sau dedupe theo rule clean.

Quy trình approve merge lại:
- Người phụ trách dữ liệu (owner team `Z11`) kiểm tra file quarantine + canonical source.
- Chỉ merge lại khi có bằng chứng sửa ở nguồn canonical hoặc rule clean được cập nhật có kiểm soát.
- Sau approve phải rerun pipeline và đối chiếu lại `cleaned_records`, `quarantine_records`, kết quả eval before/after.

---

## 4. Phiên bản & canonical

Nguồn canonical theo contract:
- `policy_refund_v4` -> `data/docs/policy_refund_v4.txt` (source of truth cho refund window = 7 ngày).
- `sla_p1_2026` -> `data/docs/sla_p1_2026.txt`.
- `it_helpdesk_faq` -> `data/docs/it_helpdesk_faq.txt`.
- `hr_leave_policy` -> `data/docs/hr_leave_policy.txt`.

Nguyên tắc versioning:
- Chính sách HR áp cutoff tối thiểu: `effective_date >= 2026-01-01`.
- Freshness SLA `24h` ưu tiên tại boundary `publish`, đồng thời theo dõi thêm boundary `ingest` để quan sát lệch giữa nguồn và snapshot publish.
- Kênh cảnh báo: `teams://z11-day10-data-alerts`.

Quy tắc thay đổi nguồn canonical:
- Khi thêm doc mới phải cập nhật đồng thời `canonical_sources`, `allowed_doc_ids`, cleaning rules và expectation liên quan.
- Mọi thay đổi version policy cần phản ánh trong report quality (before/after) để chứng minh retrieval không còn dùng bản stale.
