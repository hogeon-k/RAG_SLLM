from __future__ import annotations

import math
from datetime import datetime

import pytest

from app.config.settings import Settings
from app.database.connection import open_connection
from app.models.document import AnswerResponse, Document, DocumentChunk, ParsedCell, ParsedSheet, SearchResponse, SearchResult, VerifiedSource
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.keyword_search_repository import KeywordSearchRepository
from app.repositories.search_index_repository import SearchIndexRepository
from app.services.document_service import DocumentService
from app.services.exceptions import DocumentDeleteError
from app.services.history_service import HistoryService
from app.storage.vector_storage import ChromaVectorRepository
from tests.helpers import create_xlsx


def _settings(tmp_path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
        embedding_model="fake-e5",
        vector_collection="delete_test_chunks",
    )
    settings.ensure_directories()
    return settings


def _seed_extraction(settings: Settings, document: Document, content: str) -> list[DocumentChunk]:
    sheet = ParsedSheet(
        id=f"{document.id}-S001",
        document_id=document.id,
        sheet_name="규정",
        sheet_index=0,
        sheet_state="visible",
        max_row=2,
        max_column=2,
        non_empty_cell_count=2,
        merged_range_count=0,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    cells = [
        ParsedCell(f"{document.id}-S001-A1", document.id, sheet.id, "규정", "A1", 1, 1, "string", "제1조", None, None, None, False, False),
        ParsedCell(f"{document.id}-S001-B1", document.id, sheet.id, "규정", "B1", 1, 2, "string", content, None, None, None, False, False),
    ]
    chunks = [
        DocumentChunk(
            id=f"{document.id}-C001",
            document_id=document.id,
            sheet_id=sheet.id,
            sheet_name="규정",
            cell_start="A1",
            cell_end="B1",
            cell_range="A1:B1",
            cell_refs=("A1", "B1"),
            row_start=1,
            row_end=1,
            section=None,
            article="제1조",
            paragraph=None,
            title="삭제 테스트",
            content=content,
            chunk_index=0,
            content_hash=f"hash-{document.id}",
            created_at=datetime(2026, 1, 1, 10, 0, 0),
        )
    ]
    ExtractionRepository(settings.database_path).replace_extraction(document.id, [sheet], cells, chunks)
    return chunks


def _index_document(settings: Settings, document: Document, chunks: list[DocumentChunk]) -> ChromaVectorRepository:
    keyword_repository = KeywordSearchRepository(settings.database_path)
    vector_repository = ChromaVectorRepository(settings.vector_db_dir, settings.vector_collection, "fake-fingerprint")
    keyword_repository.index_document(document, chunks)
    vector_repository.upsert_document(document, chunks, [_vector_for_text(chunk.content) for chunk in chunks])
    SearchIndexRepository(settings.database_path).upsert_status(
        document.id,
        "READY",
        embedding_model=settings.embedding_model,
        model_fingerprint="fake-fingerprint",
        chunk_count=len(chunks),
        fts_count=len(chunks),
        vector_count=len(chunks),
        indexed_at=datetime(2026, 1, 1, 10, 1, 0),
        content_fingerprint="content-fingerprint",
    )
    DocumentRepository(settings.database_path).update_parse_status(document.id, "COMPLETED", parsed_at=datetime(2026, 1, 1, 10, 1, 0))
    return vector_repository


def _vector_for_text(text: str) -> list[float]:
    features = [3.0 if "삭제" in text else 0.1, 3.0 if "보존" in text else 0.1, 1.0]
    norm = math.sqrt(sum(value * value for value in features))
    return [value / norm for value in features]


def _save_history_snapshot(settings: Settings, document: Document) -> str:
    response = AnswerResponse(
        question="삭제 후 출처가 남나요?",
        answer="질문 이력과 검증 출처는 보존됩니다.",
        insufficient_evidence=False,
        reason="",
        used_evidence=[],
        verified_sources=[
            VerifiedSource(
                evidence_id="E1",
                chunk_id=f"{document.id}-C001",
                document_id=document.id,
                original_name=document.original_name,
                sheet_name="규정",
                article="제1조",
                title="삭제 테스트",
                cell_range="A1:B1",
                cell_refs=("A1", "B1"),
                content="질문 이력과 검증 출처는 보존됩니다.",
                used=True,
            )
        ],
        retrieval=SearchResponse(
            query="삭제 후 출처가 남나요?",
            mode="hybrid",
            results=[
                SearchResult(
                    chunk_id=f"{document.id}-C001",
                    document_id=document.id,
                    original_name=document.original_name,
                    version=document.version,
                    sheet_name="규정",
                    section=None,
                    article="제1조",
                    title="삭제 테스트",
                    content="질문 이력과 검증 출처는 보존됩니다.",
                    cell_range="A1:B1",
                    cell_refs=("A1", "B1"),
                    keyword_score=1.0,
                    vector_score=1.0,
                    final_score=1.0,
                    matched_by=("keyword", "vector"),
                    rank=1,
                )
            ],
            requested_top_k=3,
            elapsed_time_ms=1,
            keyword_candidate_count=1,
            vector_candidate_count=1,
            searched_document_ids=(document.id,),
        ),
        generation_succeeded=True,
        elapsed_time_ms=2,
    )
    return HistoryService(settings).save_answer(response).history_id


def test_delete_document_removes_internal_data_only_and_preserves_history(tmp_path) -> None:
    settings = _settings(tmp_path)
    service = DocumentService(settings)
    first_source = create_xlsx(tmp_path / "first.xlsx", "delete me")
    second_source = create_xlsx(tmp_path / "second.xlsx", "keep me")
    first = service.register_document(first_source)
    second = service.register_document(second_source)
    first_chunks = _seed_extraction(settings, first, "삭제 대상 문서")
    second_chunks = _seed_extraction(settings, second, "보존 대상 문서")
    vector_repository = _index_document(settings, first, first_chunks)
    _index_document(settings, second, second_chunks)
    history_id = _save_history_snapshot(settings, first)

    result = service.delete_document(first.id)

    assert result.display_name == "first.xlsx"
    assert result.deleted_document_count == 1
    assert result.deleted_sheet_count == 1
    assert result.deleted_cell_count == 2
    assert result.deleted_chunk_count == 1
    assert result.deleted_fts_count == 1
    assert result.deleted_vector_count == 1
    assert result.internal_file_deleted
    assert result.history_preserved
    assert first_source.exists()
    assert not (settings.data_dir / first.stored_path).exists()
    assert DocumentRepository(settings.database_path).get_by_id(first.id) is None
    assert DocumentRepository(settings.database_path).get_by_id(second.id) is not None
    assert ExtractionRepository(settings.database_path).counts_by_document(first.id) == (0, 0, 0)
    assert KeywordSearchRepository(settings.database_path).count(first.id) == 0
    assert vector_repository.count_document(first.id) == 0
    assert vector_repository.count_document(second.id) == 1
    assert SearchIndexRepository(settings.database_path).get(first.id) is None
    assert HistoryRepository(settings.database_path).get(history_id).sources[0].document_id == first.id
    assert service.register_document(first_source).original_name == "first.xlsx"


@pytest.mark.parametrize("status", ["PARSING", "INDEXING"])
def test_delete_document_blocks_active_processing_statuses(tmp_path, status: str) -> None:
    settings = _settings(tmp_path)
    document = DocumentService(settings).register_document(create_xlsx(tmp_path / "busy.xlsx"))
    DocumentRepository(settings.database_path).update_parse_status(document.id, status)

    with pytest.raises(DocumentDeleteError) as exc_info:
        DocumentService(settings).delete_document(document.id)

    assert exc_info.value.code == "DOCUMENT_BUSY"
    assert DocumentRepository(settings.database_path).get_by_id(document.id) is not None
    assert (settings.data_dir / document.stored_path).exists()


def test_delete_document_rejects_stored_path_outside_uploads_root(tmp_path) -> None:
    settings = _settings(tmp_path)
    repository = DocumentRepository(settings.database_path)
    document = Document(
        id="DOC-OUTSIDE",
        original_name="outside.xlsx",
        stored_path="../outside.xlsx",
        file_hash="hash-outside",
        file_size_bytes=1,
        version=None,
        effective_date=None,
        revised_date=None,
        department=None,
        is_latest=True,
        status="FAILED",
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    repository.create(document)

    with pytest.raises(DocumentDeleteError) as exc_info:
        DocumentService(settings).delete_document(document.id)

    assert exc_info.value.code == "INVALID_DOCUMENT_PATH"
    assert repository.get_by_id(document.id) is not None


def test_document_delete_keeps_history_sources_without_document_fk(tmp_path) -> None:
    settings = _settings(tmp_path)
    document = DocumentService(settings).register_document(create_xlsx(tmp_path / "history.xlsx"))
    history_id = _save_history_snapshot(settings, document)

    with open_connection(settings.database_path) as connection:
        source_count = connection.execute(
            "SELECT COUNT(*) FROM question_history_sources WHERE document_id = ?",
            (document.id,),
        ).fetchone()[0]

    assert source_count == 1
    assert DocumentService(settings).delete_document(document.id).history_preserved
    assert HistoryRepository(settings.database_path).get(history_id).sources[0].document_display_name == "history.xlsx"
