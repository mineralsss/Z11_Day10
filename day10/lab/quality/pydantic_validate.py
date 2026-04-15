"""
Pydantic schema validation cho cleaned rows.

Mục tiêu: chặn schema drift sớm trước expectation/embed.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class CleanedRowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    chunk_text: str
    effective_date: date
    exported_at: datetime

    @field_validator("chunk_id", "doc_id")
    @classmethod
    def _non_empty_id(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("must not be empty")
        return s

    @field_validator("chunk_text")
    @classmethod
    def _chunk_min_len(cls, v: str) -> str:
        s = (v or "").strip()
        if len(s) < 8:
            raise ValueError("chunk_text must be at least 8 chars")
        return s

    @field_validator("exported_at")
    @classmethod
    def _timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


def validate_cleaned_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    validated: List[Dict[str, Any]] = []
    errors: List[str] = []

    for idx, row in enumerate(rows, start=1):
        try:
            model = CleanedRowModel.model_validate(row)
            validated.append(
                {
                    "chunk_id": model.chunk_id,
                    "doc_id": model.doc_id,
                    "chunk_text": model.chunk_text,
                    "effective_date": model.effective_date.isoformat(),
                    "exported_at": model.exported_at.replace(microsecond=0).isoformat(),
                }
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(x) for x in first.get("loc", []))
            msg = first.get("msg", "validation error")
            errors.append(f"row={idx} field={loc} error={msg}")

    return validated, errors
