from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class Document:
    id: str
    original_name: str
    stored_path: str
    file_hash: str
    file_size_bytes: int
    version: str | None
    effective_date: date | None
    revised_date: date | None
    department: str | None
    is_latest: bool
    status: str
    error_message: str | None
    uploaded_at: datetime


@dataclass(frozen=True)
class DocumentRegistration:
    source_path: Path
    version: str | None = None
    effective_date: date | None = None
    revised_date: date | None = None
    department: str | None = None

