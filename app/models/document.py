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
    parsed_at: datetime | None = None
    parse_error: str | None = None


@dataclass(frozen=True)
class DocumentRegistration:
    source_path: Path
    version: str | None = None
    effective_date: date | None = None
    revised_date: date | None = None
    department: str | None = None


@dataclass(frozen=True)
class ParsedSheet:
    id: str
    document_id: str
    sheet_name: str
    sheet_index: int
    sheet_state: str
    max_row: int
    max_column: int
    non_empty_cell_count: int
    merged_range_count: int
    created_at: datetime


@dataclass(frozen=True)
class ParsedCell:
    id: str
    document_id: str
    sheet_id: str
    sheet_name: str
    coordinate: str
    row_index: int
    column_index: int
    value_type: str
    text_value: str
    formula: str | None
    cached_value: str | None
    merged_range: str | None
    is_merged_anchor: bool
    is_hidden: bool


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    sheet_id: str
    sheet_name: str
    cell_start: str
    cell_end: str
    cell_range: str
    cell_refs: tuple[str, ...]
    row_start: int
    row_end: int
    section: str | None
    article: str | None
    paragraph: str | None
    title: str | None
    content: str
    chunk_index: int
    content_hash: str
    created_at: datetime


@dataclass(frozen=True)
class ParsedWorkbook:
    document_id: str
    sheets: tuple[ParsedSheet, ...]
    cells: tuple[ParsedCell, ...]
    skipped_hidden_sheet_count: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    document_id: str
    sheet_count: int
    skipped_hidden_sheet_count: int
    non_empty_cell_count: int
    merged_range_count: int
    chunk_count: int
    status: str
    elapsed_time_ms: int
    warnings: tuple[str, ...] = ()
