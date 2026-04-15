# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** ___________  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| ___ | Ingestion / Raw Owner | ___ |
| ___ | Cleaning & Quality Owner | ___ |
| ___ | Embed & Idempotency Owner | ___ |
| ___ | Monitoring / Docs Owner | ___ |

**Ngày nộp:** ___________  
**Repo:** ___________  
**Độ dài khuyến nghị:** 600–1000 từ

---

> **Nộp tại:** `reports/group_report.md`  
> **Deadline commit:** xem `SCORING.md` (code/trace sớm; report có thể muộn hơn nếu được phép).  
> Phải có **run_id**, **đường dẫn artifact**, và **bằng chứng before/after** (CSV eval hoặc screenshot).

---

## 1. Pipeline tổng quan (150–200 từ)

> Nguồn raw là gì (CSV mẫu / export thật)? Chuỗi lệnh chạy end-to-end? `run_id` lấy ở đâu trong log?

**Tóm tắt luồng:**

Nhóm dùng raw export mẫu `data/raw/policy_export_dirty.csv`, chạy pipeline chuẩn qua `python etl_pipeline.py run`, sau đó kiểm tra manifest, quarantine và eval. Pipeline đọc raw, clean theo allowlist/versioning, quarantine các record lỗi, chạy Pydantic schema gate + expectation suite, upsert vào Chroma, rồi ghi manifest và freshness ở 2 boundary (ingest + publish). Run gần nhất có `run_id=2026-04-15T09-52Z` trong log và các artifact đi kèm nằm trong `artifacts/manifests/`, và `artifacts/logs/`.

**Lệnh chạy một dòng (copy từ README thực tế của nhóm):**

`python etl_pipeline.py run`

---

## 2. Cleaning & expectation (150–200 từ)

> Baseline đã có nhiều rule (allowlist, ngày ISO, HR stale, refund, dedupe…). Nhóm thêm **≥3 rule mới** + **≥2 expectation mới**. Khai báo expectation nào **halt**.

### 2a. Bảng metric_impact (bắt buộc — chống trivial)

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| Embed idempotent / prune stale ids | collection count = 10 sau run đầu | collection count = 10 sau rerun thứ hai, không phình tài nguyên | `artifacts/logs/run_2026-04-15T09-45Z.log`, `artifacts/logs/run_2026-04-15T09-52Z.log`, kiểm tra collection count = 10 sau rerun |
| `pydantic_validate` (schema gate) | 0 lỗi schema trên cleaned hiện tại | 0 lỗi schema sau rerun | `pydantic_validate OK rows=10` trong log chuẩn gần nhất |
| `chunk_id_unique_non_empty` | 0 lỗi trên cleaned hiện tại | 0 lỗi sau rerun | `expectation[chunk_id_unique_non_empty] OK (halt)` trong log hai run gần nhất |
| `exported_at_iso_datetime` | 0 lỗi trên cleaned hiện tại | 0 lỗi sau rerun | `expectation[exported_at_iso_datetime] OK (halt)` trong log hai run gần nhất |
| `refund_no_stale_14d_window` | 0 vi phạm sau fix | 0 vi phạm sau rerun | `expectation[refund_no_stale_14d_window] OK (halt)` trong log |
| `stale_refund_migration_note` | quarantine_records = 5, cleaned_records = 10 | quarantine_records = 6, cleaned_records = 9 khi inject-bad (no-refund-fix) | `artifacts/logs/run_inject-bad.log`, `artifacts/quarantine/quarantine_inject-bad.csv`, `embed_prune_removed=9` |

### 2b. Mapping expectation theo 6 dimensions

| Expectation | Dimension | Severity | Metric / signal trong log |
|-------------|-----------|----------|----------------------------|
| `min_one_row` | Completeness | halt | `cleaned_rows` |
| `no_empty_doc_id` | Completeness | halt | `empty_doc_id_count` |
| `effective_date_null_rate_le_5pct` | Completeness / Distribution | warn | `null_rate`, `null_count` |
| `refund_no_stale_14d_window` | Accuracy | halt | `violations` |
| `hr_leave_no_stale_10d_annual` | Accuracy | halt | `violations` |
| `effective_date_iso_yyyy_mm_dd` | Consistency | halt | `non_iso_rows` |
| `exported_at_iso_datetime` | Consistency | halt | `non_iso_datetime_rows` |
| `cross_field_doc_policy_consistency` | Cross-field consistency | warn | `violations` |
| `chunk_min_length_8` | Length | warn | `short_chunks` |
| `chunk_length_no_long_anomaly` | Length / Anomaly | warn | `too_long_rows` |
| `chunk_id_unique_non_empty` | Uniqueness | halt | `duplicate_or_empty_ids` |
| `doc_id_cardinality_not_collapsed` | Cardinality | warn | `unique_doc_ids`, `ratio` |
| `language_entropy_no_ocr_spike` | Entropy / language | warn | `noisy_rows` |
| `effective_date_no_time_travel` | Time travel | halt | `future_rows` |

Ghi chú:
- Freshness (`PASS/WARN/FAIL`) được đo ở monitoring theo manifest, không nằm trong expectation suite.
- `hits_forbidden` trong eval quét toàn bộ top-k ghép lại để bắt stale context dù top-1 có thể trông đúng.

**Rule chính (baseline + mở rộng):**

- Baseline giữ allowlist `doc_id`, chuẩn hóa `effective_date`, quarantine HR cũ, fix refund 14→7, dedupe chunk_text.
- Mở rộng thêm text sanitize, validate/export `exported_at`, guard chunk quá dài, unique `chunk_id`, kiểm tra ISO datetime, và quarantine migration-note stale refund khi demo inject.
- Embed luôn upsert theo `chunk_id` và prune id không còn trong cleaned snapshot để tránh stale vector.

**Ví dụ 1 lần expectation fail (nếu có) và cách xử lý:**

Freshness vẫn FAIL do raw snapshot cũ: `freshness_check=FAIL` với `latest_exported_at=2026-04-10T08:00:00+00:00`. Cách xử lý là ghi rõ trong runbook rằng đây là dữ liệu snapshot cũ, hoặc nới `FRESHNESS_SLA_HOURS` nếu cần demo, nhưng run nộp bài chuẩn vẫn giữ pipeline `exit 0`.

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

> Bắt buộc: inject corruption (Sprint 3) — mô tả + dẫn `artifacts/eval/…` hoặc log.

**Kịch bản inject:**

Nhóm chạy `python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate` để cố ý giữ stale refund context và ép expectation `refund_no_stale_14d_window` fail trước khi thêm rule migration-note quarantine. Sau rule mới, record refund cũ bị tách khỏi cleaned snapshot nên `quarantine_records` tăng từ 5 lên 6, `cleaned_records` giảm từ 10 xuống 9, và `embed_prune_removed=9` cho thấy index đã prune stale ids thay vì giữ vector cũ.

**Kết quả định lượng (từ CSV / bảng):**

`artifacts/eval/before_after_eval.csv` cho thấy các câu chuẩn vẫn trả đúng doc mục tiêu: `contains_expected=yes` và `hits_forbidden=no` trên toàn bộ top-k. Trong `artifacts/eval/after_inject_bad.csv`, `q_leave_version` vẫn đúng `top1_doc_expected=yes`, còn `q_refund_window` tiếp tục đi vào `policy_refund_v4` nhưng stale refund chunk 14 ngày không còn nằm trong cleaned index của inject-bad. Như vậy lỗi refund stale được chặn ở boundary clean/publish, không chỉ ở retrieval.

---

## 4. Freshness & monitoring (100–150 từ)

> SLA bạn chọn, ý nghĩa PASS/WARN/FAIL trên manifest mẫu.

SLA freshness của nhóm là 24 giờ và đo ở 2 boundary. Boundary `ingest` dùng `ingest_latest_exported_at` lấy từ raw export; boundary `publish` dùng `publish_latest_exported_at` sau clean trước khi publish index. `PASS` nghĩa là timestamp trong SLA; `WARN` là thiếu timestamp; `FAIL` là vượt SLA. Ở run mới nhất, cả hai boundary đều `FAIL` vì dữ liệu mẫu có `exported_at` cũ (`2026-04-10T08:00:00`). Dòng `freshness_check=...` được giữ như alias tương thích ngược và tương đương với boundary publish.

---

## 5. Liên hệ Day 09 (50–100 từ)

> Dữ liệu sau embed có phục vụ lại multi-agent Day 09 không? Nếu có, mô tả tích hợp; nếu không, giải thích vì sao tách collection.

Có. Corpus sau clean được upsert vào collection `day10_kb` để dùng lại cho retrieval/eval của Day 09, nhưng nhóm giữ collection riêng để tách snapshot Day 10 khỏi index cũ của Day 09. Cách này cho phép so sánh before/after theo `run_id` và tránh vector stale làm sai grading. Khi cần, Day 09 chỉ đọc corpus đã publish thay vì đọc raw export trực tiếp.

---

## 6. Rủi ro còn lại & việc chưa làm

- Freshness vẫn FAIL trên snapshot mẫu ở cả ingest và publish vì `exported_at` cũ hơn SLA 24h; đây là rủi ro dữ liệu, không phải lỗi pipeline.
- `after_inject_bad.csv` cho thấy retrieval vẫn cần theo dõi thêm top-k preview nếu lớp chấm muốn bắt lỗi context đúng hơn chỉ top1 doc.