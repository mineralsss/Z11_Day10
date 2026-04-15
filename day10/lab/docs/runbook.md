# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

Triệu chứng thường gặp:
- Agent trả lời sai policy refund (14 ngày thay vì 7 ngày).
- Kết quả retrieval có `hits_forbidden=true` hoặc top-1 lệch doc mong đợi.
- Pipeline chạy xong nhưng dữ liệu bị báo stale do freshness SLA.

---

## Detection

Tín hiệu phát hiện:
- `expectation[refund_no_stale_14d_window] FAIL` hoặc expectation halt khác trong log pipeline.
- `pydantic_validate FAIL invalid_rows=<n>` trong log pipeline (schema cleaned không hợp lệ).
- `freshness_check=FAIL` trong log run và manifest.
- `freshness_ingest=<PASS|WARN|FAIL>` và `freshness_publish=<PASS|WARN|FAIL>` để so sánh 2 boundary.
- File eval có `hits_forbidden=true` hoặc `top1_doc_matches=false`.
- `quarantine_records` tăng bất thường sau ingest/inject.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Kiểm tra `artifacts/manifests/*.json` (run mới nhất) | Xác định `run_id`, `latest_exported_at`, `cleaned_records`, `quarantine_records` |
| 2 | Mở `artifacts/quarantine/*.csv` | Thấy rõ lý do bị loại (`unknown_doc_id`, `stale_hr_policy_effective_date`, `invalid_exported_at_format`, ...) |
| 3 | Đọc `artifacts/logs/run_<run_id>.log` | Xác định expectation nào fail/halt, có `pydantic_validate FAIL` hay không, và có dùng `--skip-validate` hay không |
| 4 | Nếu có schema fail, đọc các dòng `pydantic_error row=... field=... error=...` | Khoanh đúng field gây lỗi (`chunk_id`, `doc_id`, `chunk_text`, `effective_date`, `exported_at`) |
| 5 | Chạy `python eval_retrieval.py --out artifacts/eval/before_after_eval.csv` | So sánh `contains_expected`, `hits_forbidden`, `top1_doc_matches` trước/sau fix |

---

## Mitigation

Hành động khắc phục chuẩn:
- Sửa dữ liệu nguồn canonical hoặc rule clean gây fail.
- Nếu lỗi Pydantic: sửa record lỗi theo `row/field` trong log (đặc biệt `exported_at` timezone-aware, `chunk_text` >= 8 ký tự, không field thừa).
- Chạy lại pipeline chuẩn:
	- `python etl_pipeline.py run`
	- Không dùng `--skip-validate` trong run nộp bài (trừ khi demo inject có ghi rõ lý do).
- Chỉ dùng `--skip-validate` khi demo có chủ đích; phải ghi rõ trong report vì có rủi ro publish dữ liệu chưa đạt schema contract.
- Nếu đã lỡ inject dữ liệu xấu, rerun pipeline chuẩn để overwrite index snapshot và prune id stale.
- Nếu freshness fail do snapshot cũ, chọn một trong hai:
	- cập nhật `exported_at` nguồn theo dữ liệu mới, hoặc
	- điều chỉnh `FRESHNESS_SLA_HOURS` phù hợp và ghi giải thích trong report.

Bằng chứng run chuẩn gần nhất:
- Lệnh: `python etl_pipeline.py run`
- Schema gate: `pydantic_validate OK rows=10`
- Kết quả: `PIPELINE_OK` và **exit code 0**.
- Run id: `2026-04-15T09-52Z`.
- Kết quả chính: `cleaned_records=10`, `quarantine_records=5`.
- Lưu ý: freshness vẫn FAIL ở cả ingest và publish vì `latest_exported_at=2026-04-10T08:00:00(+00:00)` vượt SLA 24h.

Ghi chú (freshness trên data mẫu):
- `freshness_check=FAIL` với CSV mẫu là hợp lý vì `exported_at` cố ý cũ.
- Nhóm cần ghi rõ trong report/runbook SLA đang áp cho `data snapshot` hay cho `pipeline run`.
- Có thể chọn một trong hai cách để PASS:
	- tăng `FRESHNESS_SLA_HOURS` theo ngữ cảnh đánh giá, hoặc
	- cập nhật `exported_at` rồi rerun.
- Quan trọng nhất là giải thích nhất quán với boundary đo freshness đã chọn.

Boundary freshness bắt buộc (ingest + publish):
- `ingest`: đo theo `ingest_latest_exported_at` (timestamp mới nhất nhìn thấy ở raw export ngay sau load).
- `publish`: đo theo `publish_latest_exported_at` (timestamp mới nhất của cleaned snapshot trước khi publish index).
- Log minh chứng trong mỗi run:
	- `freshness_ingest=... {..."boundary":"ingest"...}`
	- `freshness_publish=... {..."boundary":"publish"...}`
- Trường hợp 2 boundary lệch nhau là tín hiệu có biến đổi trong pipeline (quarantine/drop/parse) cần điều tra thêm.

---

## Prevention

Ngăn ngừa tái diễn:
- Duy trì gate expectation `halt` cho rule nghiệp vụ quan trọng (refund window, exported_at format, chunk_id unique).
- Giữ Pydantic schema validation bật mặc định trước expectation/embed để chặn schema drift sớm.
- Theo dõi alert channel `teams://z11-day10-data-alerts` khi freshness vượt SLA.
- Gán owner rõ ràng theo vai: Ingestion, Cleaning/Quality, Embed, Monitoring/Docs.
- Cập nhật đồng bộ `contracts/data_contract.yaml` khi thêm doc/rule mới.
- Mỗi rule/expectation mới bắt buộc có `metric_impact` trong group report để tránh thay đổi trivial.
