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
    lifecycle_status: str = "CURRENT"
    version_label: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    document_family: str | None = None
    supersedes_document_id: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DocumentRegistration:
    source_path: Path
    version: str | None = None
    effective_date: date | None = None
    revised_date: date | None = None
    department: str | None = None


@dataclass(frozen=True)
class DocumentDeleteResult:
    document_id: str
    display_name: str
    deleted_document_count: int
    deleted_sheet_count: int
    deleted_cell_count: int
    deleted_chunk_count: int
    deleted_fts_count: int
    deleted_vector_count: int
    internal_file_deleted: bool
    history_preserved: bool
    warning_code: str | None = None


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


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    document_id: str
    original_name: str
    version: str | None
    sheet_name: str
    section: str | None
    article: str | None
    title: str | None
    content: str
    cell_range: str
    cell_refs: tuple[str, ...]
    keyword_score: float | None
    vector_score: float | None
    final_score: float
    matched_by: tuple[str, ...]
    rank: int


@dataclass(frozen=True)
class SearchResponse:
    query: str
    mode: str
    results: list[SearchResult]
    requested_top_k: int
    elapsed_time_ms: int
    keyword_candidate_count: int
    vector_candidate_count: int
    searched_document_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    chunk_id: str
    document_id: str
    rank: int
    retrieval_score: float
    article: str | None
    title: str | None
    content: str


@dataclass(frozen=True)
class EvidenceSufficiencyResult:
    sufficient: bool
    confidence_level: str
    reason_code: str
    reason: str
    best_chunk_id: str | None
    keyword_hit: bool
    exact_article_hit: bool
    lexical_coverage: float
    vector_similarity: float | None
    source_hint_match: bool
    version_intent_match: bool
    conflicting_evidence: bool
    evaluated_evidence_count: int


@dataclass(frozen=True)
class VerifiedSource:
    evidence_id: str
    chunk_id: str
    document_id: str
    original_name: str
    sheet_name: str
    article: str | None
    title: str | None
    cell_range: str
    cell_refs: tuple[str, ...]
    content: str
    used: bool


@dataclass(frozen=True)
class AnswerResponse:
    question: str
    answer: str
    insufficient_evidence: bool
    reason: str
    used_evidence: list[Evidence]
    verified_sources: list[VerifiedSource]
    retrieval: SearchResponse
    generation_succeeded: bool
    elapsed_time_ms: int
    error_code: str | None = None
    action_items: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    generation_retry_count: int = 0
    sufficiency: EvidenceSufficiencyResult | None = None
    generation_mode: str = "normal"
    fallback_used: bool = False


@dataclass(frozen=True)
class HistorySource:
    history_source_id: str
    history_id: str
    evidence_id: str
    chunk_id: str
    document_id: str
    sheet_id: str | None
    source_rank: int
    document_display_name: str
    sheet_name: str
    article: str | None
    title: str | None
    cell_range: str
    cell_refs: tuple[str, ...]
    content: str
    created_at: datetime


@dataclass(frozen=True)
class QuestionHistory:
    history_id: str
    request_id: str
    question: str
    answer: str
    status: str
    insufficient_evidence: bool
    error_code: str | None
    error_message: str | None
    search_mode: str
    requested_top_k: int
    retrieved_count: int
    used_evidence_count: int
    ollama_model: str | None
    total_duration_ms: int
    retrieval_duration_ms: int
    generation_duration_ms: int
    created_at: datetime
    sources: tuple[HistorySource, ...] = ()


@dataclass(frozen=True)
class HistoryListResult:
    items: list[QuestionHistory]
    total_count: int
    limit: int
    offset: int


@dataclass(frozen=True)
class HistoryFilters:
    search_text: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class IndexingResult:
    document_id: str
    fts_count: int
    vector_count: int
    embedding_model: str
    status: str
    elapsed_time_ms: int
    warnings: tuple[str, ...] = ()
