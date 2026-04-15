# Quality report — Lab Day 10 (nhóm)

**run_id:** `2026-04-15T09-52Z`
**Ngày:** `2026-04-15`

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước | Sau | Ghi chú |
|--------|-------|-----|---------|
| raw_records | 15 (`inject-bad`) | 15 (`2026-04-15T09-52Z`) | cùng nguồn `data/raw/policy_export_dirty.csv` |
| cleaned_records | 9 (`inject-bad`, log mới nhất) | 10 (`2026-04-15T09-52Z`) | sau run chuẩn tăng +1 cleaned row |
| quarantine_records | 6 (`inject-bad`, log mới nhất) | 5 (`2026-04-15T09-52Z`) | sau run chuẩn giảm -1 quarantine row |
| Expectation halt? | Không halt ở log `inject-bad` mới nhất; có bản ghi inject trước đó từng fail `refund_no_stale_14d_window` | Không halt (`PIPELINE_OK`) | inject chạy với `--skip-validate`; run chuẩn không dùng skip |

---

## 2. Before / after retrieval (bắt buộc)

> Đính kèm hoặc dẫn link tới `artifacts/eval/before_after_eval.csv` (hoặc 2 file before/after).

**Câu hỏi then chốt:** refund window (`q_refund_window`)  
**Trước (after_inject_bad.csv):**

`q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền kể từ khi xác nhận đơn?,policy_refund_v4,Khách hàng cần cung cấp mã đơn hàng hợp lệ khi gửi yêu cầu hoàn tiền.,yes,no,,3`

**Sau (before_after_eval.csv):**

`q_refund_window,Khách hàng có bao nhiêu ngày để yêu cầu hoàn tiền kể từ khi xác nhận đơn?,policy_refund_v4,Khách hàng cần cung cấp mã đơn hàng hợp lệ khi gửi yêu cầu hoàn tiền.,yes,no,,3`

Nhận xét: dòng `q_refund_window` giống nhau giữa before/after (`contains_expected=yes`, `hits_forbidden=no`).

**Merit (khuyến nghị):** versioning HR — `q_leave_version` (`contains_expected`, `hits_forbidden`, cột `top1_doc_expected`)

**Trước (after_inject_bad.csv):**

`q_leave_version,"Theo chính sách nghỉ phép hiện hành (2026), nhân viên dưới 3 năm kinh nghiệm được bao nhiêu ngày phép năm?",hr_leave_policy,Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026.,yes,no,yes,3`

**Sau (before_after_eval.csv):**

`q_leave_version,"Theo chính sách nghỉ phép hiện hành (2026), nhân viên dưới 3 năm kinh nghiệm được bao nhiêu ngày phép năm?",hr_leave_policy,Nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm theo chính sách 2026.,yes,no,yes,3`

Nhận xét: dòng `q_leave_version` cũng giống nhau giữa before/after (`contains_expected=yes`, `hits_forbidden=no`, `top1_doc_expected=yes`).

Kết luận cho bộ câu hỏi hiện tại:
- Chưa quan sát được chênh lệch retrieval metric giữa before/after trên 4 câu test đang dùng.
- Bằng chứng before/after trong bài này chủ yếu thể hiện qua pipeline metrics/log (`cleaned_records`, `quarantine_records`, expectation, `embed_prune_removed`) hơn là qua CSV eval hiện tại.

---

## 3. Freshness & monitor

> Ghi cả 2 boundary với log minh chứng:
> - `freshness_ingest` (PASS/WARN/FAIL)
> - `freshness_publish` (PASS/WARN/FAIL)
> Có thể kèm `freshness_check` như alias backward-compatible cho publish.
>
Log minh chứng (run `2026-04-15T09-52Z`):
- `freshness_ingest=FAIL {"boundary": "ingest", "latest_exported_at": "2026-04-10T08:00:00", "age_hours": 121.878, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`
- `freshness_publish=FAIL {"boundary": "publish", "latest_exported_at": "2026-04-10T08:00:00+00:00", "age_hours": 121.878, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`
- `freshness_check=FAIL {"boundary": "publish", "latest_exported_at": "2026-04-10T08:00:00+00:00", "age_hours": 121.878, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}`

Diễn giải SLA:
- SLA hiện tại là 24 giờ và đang áp cho data snapshot.
- CSV mẫu có `exported_at` cũ (2026-04-10), nên FAIL ở cả ingest và publish là hợp lý.
- `freshness_check` được giữ để tương thích ngược và phản ánh boundary publish.

---

## 4. Corruption inject (Sprint 3)

> Mô tả cố ý làm hỏng dữ liệu kiểu gì (duplicate / stale / sai format) và cách phát hiện.

Kịch bản inject đã chạy:
- Lệnh: `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate`.
- Dấu hiệu phát hiện trong log `run_inject-bad.log`:
- Run inject mới nhất cho thấy: `cleaned_records=9`, `quarantine_records=6`, `embed_prune_removed=9`, `PIPELINE_OK`.
- Loại corruption: stale / version drift của refund policy, cụ thể là chunk còn mang dấu vết policy-v3 / lỗi migration hoặc cửa sổ 14 ngày thay vì 7 ngày.
- Không phải duplicate và cũng không phải sai format; lỗi này là semantic stale content nên phải bắt bằng expectation + quarantine theo rule refund.
- Kết luận: inject tạo tác động đo được lên pipeline metrics (cleaned/quarantine, prune), dù CSV eval top-k hiện tại vẫn cho `contains_expected=yes` và `hits_forbidden=no`.

---

## 5. Hạn chế & việc chưa làm

- Chưa có sự khác biệt rõ trong `before_after_eval.csv` và `after_inject_bad.csv` cho bộ câu hỏi hiện tại; cần mở rộng bộ câu để tăng độ nhạy với stale context.
- Freshness vẫn FAIL do dữ liệu snapshot cũ; nếu cần PASS phải đổi SLA hoặc cập nhật timestamp có chủ đích và ghi rõ rationale.
- `run_inject-bad.log` có nhiều lần chạy nối tiếp; khi chấm nên chỉ rõ block log theo timestamp/run context để tránh nhầm kết quả cũ/mới.
