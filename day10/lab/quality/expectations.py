"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # E7: chunk_id phải unique (bảo đảm idempotent upsert không đè sai bản ghi)
    ids = [(r.get("chunk_id") or "").strip() for r in cleaned_rows]
    dup_ids = len(ids) - len(set(ids))
    ok7 = dup_ids == 0 and all(ids)
    results.append(
        ExpectationResult(
            "chunk_id_unique_non_empty",
            ok7,
            "halt",
            f"duplicate_or_empty_ids={dup_ids if dup_ids > 0 else sum(1 for x in ids if not x)}",
        )
    )

    # E8: exported_at phải ở dạng ISO datetime sau clean
    dt_bad = [
        r
        for r in cleaned_rows
        if not re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+\d{2}:\d{2}|Z)$",
            (r.get("exported_at") or "").strip(),
        )
    ]
    ok8 = len(dt_bad) == 0
    results.append(
        ExpectationResult(
            "exported_at_iso_datetime",
            ok8,
            "halt",
            f"non_iso_datetime_rows={len(dt_bad)}",
        )
    )

    # E9: null rate effective_date không vượt ngưỡng (anomaly theo distribution)
    total = len(cleaned_rows)
    null_eff = sum(1 for r in cleaned_rows if not (r.get("effective_date") or "").strip())
    null_rate = (null_eff / total) if total else 0.0
    ok9 = null_rate <= 0.05
    results.append(
        ExpectationResult(
            "effective_date_null_rate_le_5pct",
            ok9,
            "warn",
            f"null_rate={null_rate:.3f}; null_count={null_eff}; total={total}",
        )
    )

    # E10: length anomaly — phát hiện content quá dài bất thường
    long_rows = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) > 1200]
    ok10 = len(long_rows) == 0
    results.append(
        ExpectationResult(
            "chunk_length_no_long_anomaly",
            ok10,
            "warn",
            f"too_long_rows={len(long_rows)}",
        )
    )

    # E11: cardinality — số doc_id unique không sụt mạnh
    uniq_doc_ids = {str(r.get("doc_id") or "").strip() for r in cleaned_rows if (r.get("doc_id") or "").strip()}
    uniq_count = len(uniq_doc_ids)
    cardinality_ratio = (uniq_count / total) if total else 0.0
    ok11 = uniq_count >= 2 and cardinality_ratio >= 0.15
    results.append(
        ExpectationResult(
            "doc_id_cardinality_not_collapsed",
            ok11,
            "warn",
            f"unique_doc_ids={uniq_count}; ratio={cardinality_ratio:.3f}",
        )
    )

    # E12: entropy/language — phát hiện dấu hiệu OCR noise (ký tự thay thế, tỷ lệ ký tự chữ quá thấp)
    def _is_ocr_noisy(text: str) -> bool:
        s = (text or "").strip()
        if not s:
            return False
        if "�" in s or "\ufffd" in s:
            return True
        letters = sum(1 for ch in s if ch.isalpha())
        ratio = letters / max(1, len(s))
        return ratio < 0.35

    noisy_rows = [r for r in cleaned_rows if _is_ocr_noisy(str(r.get("chunk_text") or ""))]
    ok12 = len(noisy_rows) == 0
    results.append(
        ExpectationResult(
            "language_entropy_no_ocr_spike",
            ok12,
            "warn",
            f"noisy_rows={len(noisy_rows)}",
        )
    )

    # E13: cross-field — tính nhất quán doc_id với nội dung nghiệp vụ chính
    cross_bad = []
    for r in cleaned_rows:
        doc_id = r.get("doc_id")
        text = (r.get("chunk_text") or "")
        if doc_id == "sla_p1_2026" and "15 phút" not in text:
            cross_bad.append(r)
            continue
        # Chỉ kiểm những chunk refund nói về cửa sổ theo ngày để tránh false positive.
        if doc_id == "policy_refund_v4" and "ngày làm việc" in text:
            if "7 ngày" not in text or "14 ngày" in text:
                cross_bad.append(r)
    ok13 = len(cross_bad) == 0
    results.append(
        ExpectationResult(
            "cross_field_doc_policy_consistency",
            ok13,
            "warn",
            f"violations={len(cross_bad)}",
        )
    )

    # E14: time travel — effective_date không được ở tương lai quá 1 ngày
    today = datetime.now(timezone.utc).date()
    future_rows = []
    for r in cleaned_rows:
        raw = (r.get("effective_date") or "").strip()
        try:
            d = datetime.fromisoformat(raw).date()
            if (d - today).days > 1:
                future_rows.append(r)
        except ValueError:
            # Đã có expectation ISO riêng (E5); bỏ qua tại đây.
            continue
    ok14 = len(future_rows) == 0
    results.append(
        ExpectationResult(
            "effective_date_no_time_travel",
            ok14,
            "halt",
            f"future_rows={len(future_rows)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
