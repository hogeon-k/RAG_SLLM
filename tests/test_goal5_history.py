from __future__ import annotations

from datetime import datetime

import pytest

from app.config.settings import Settings
from app.models.document import AnswerResponse, HistorySource, QuestionHistory, SearchResponse, SearchResult, VerifiedSource
from app.repositories.history_repository import HistoryRepository
from app.services.exceptions import AnswerGenerationError, DocumentRegistrationError
from app.services.history_service import HistoryService
from app.services.question_service import QuestionService


def _settings(tmp_path) -> Settings:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
        ollama_model="fake-model",
        retrieval_top_k=3,
    )
    settings.ensure_directories()
    return settings


def _retrieval() -> SearchResponse:
    return SearchResponse(
        query="leave",
        mode="hybrid",
        results=[
            SearchResult(
                chunk_id="CHUNK-1",
                document_id="DOC-1",
                original_name="rules.xlsx",
                version=None,
                sheet_name="Leave",
                section=None,
                article="Article 8",
                title="Annual leave",
                content="Apply three days before leave.",
                cell_range="A1:B2",
                cell_refs=("A1", "B2"),
                keyword_score=1.0,
                vector_score=1.0,
                final_score=0.9,
                matched_by=("keyword", "vector"),
                rank=1,
            )
        ],
        requested_top_k=3,
        elapsed_time_ms=11,
        keyword_candidate_count=1,
        vector_candidate_count=1,
        searched_document_ids=("DOC-1",),
    )


def _answer(question: str = "leave") -> AnswerResponse:
    return AnswerResponse(
        question=question,
        answer="Apply three days before leave.",
        insufficient_evidence=False,
        reason="",
        used_evidence=[],
        verified_sources=[
            VerifiedSource(
                evidence_id="E1",
                chunk_id="CHUNK-1",
                document_id="DOC-1",
                original_name="rules.xlsx",
                sheet_name="Leave",
                article="Article 8",
                title="Annual leave",
                cell_range="A1:B2",
                cell_refs=("A1", "B2"),
                content="Apply three days before leave.",
                used=True,
            )
        ],
        retrieval=_retrieval(),
        generation_succeeded=True,
        elapsed_time_ms=31,
    )


def test_history_service_saves_answer_and_source_snapshot(tmp_path) -> None:
    service = HistoryService(_settings(tmp_path))

    saved = service.save_answer(_answer())
    detail = service.get_history(saved.history_id)

    assert detail.status == "SUCCESS"
    assert detail.answer == "Apply three days before leave."
    assert detail.sources[0].document_display_name == "rules.xlsx"
    assert detail.sources[0].cell_range == "A1:B2"
    assert detail.sources[0].content == "Apply three days before leave."


def test_history_repository_lists_filters_and_paginates(tmp_path) -> None:
    service = HistoryService(_settings(tmp_path))
    service.save_answer(_answer("annual leave"))
    service.save_failure("broken model", "hybrid", "OLLAMA_UNAVAILABLE", "Ollama server is unavailable.")

    success = service.list_histories(status="SUCCESS")
    failed = service.list_histories(search_text="broken", status="FAILED", limit=1, offset=0)
    escaped = service.list_histories(search_text="%_\\")

    assert success.total_count == 1
    assert failed.total_count == 1
    assert failed.items[0].status == "FAILED"
    assert escaped.total_count == 0


def test_history_date_filter_and_missing_detail(tmp_path) -> None:
    service = HistoryService(_settings(tmp_path))
    saved = service.save_answer(_answer("annual leave"))

    assert service.list_histories(start_date=saved.created_at.date(), end_date=saved.created_at.date()).total_count == 1
    assert service.list_histories(start_date=saved.created_at.date().replace(year=2030)).total_count == 0
    with pytest.raises(DocumentRegistrationError):
        service.get_history("missing")


def test_history_delete_does_not_remove_documents_or_chunks(tmp_path) -> None:
    settings = _settings(tmp_path)
    service = HistoryService(settings)
    saved = service.save_answer(_answer())
    repository = HistoryRepository(settings.database_path)

    assert repository.count() == 1
    assert service.delete_history(saved.history_id)
    assert repository.count() == 0


def test_history_repository_rolls_back_when_source_insert_fails(tmp_path) -> None:
    settings = _settings(tmp_path)
    repository = HistoryRepository(settings.database_path)
    now = datetime(2026, 1, 1, 10, 0, 0)
    duplicate_source = HistorySource(
        history_source_id="HSRC-1",
        history_id="HIST-1",
        evidence_id="E1",
        chunk_id="CHUNK-1",
        document_id="DOC-1",
        sheet_id=None,
        source_rank=1,
        document_display_name="rules.xlsx",
        sheet_name="Leave",
        article="Article 8",
        title="Annual leave",
        cell_range="A1:B2",
        cell_refs=("A1", "B2"),
        content="content",
        created_at=now,
    )
    history = QuestionHistory(
        history_id="HIST-1",
        request_id="REQ-1",
        question="question",
        answer="answer",
        status="SUCCESS",
        insufficient_evidence=False,
        error_code=None,
        error_message=None,
        search_mode="hybrid",
        requested_top_k=3,
        retrieved_count=1,
        used_evidence_count=2,
        ollama_model="fake-model",
        total_duration_ms=1,
        retrieval_duration_ms=1,
        generation_duration_ms=0,
        created_at=now,
        sources=(duplicate_source, duplicate_source),
    )

    with pytest.raises(Exception):
        repository.save(history)

    assert repository.count() == 0


def test_history_delete_all_returns_count(tmp_path) -> None:
    service = HistoryService(_settings(tmp_path))
    service.save_answer(_answer("q1"))
    service.save_answer(_answer("q2"))

    assert service.delete_all() == 2
    assert service.count() == 0


def test_history_service_rejects_invalid_filters(tmp_path) -> None:
    service = HistoryService(_settings(tmp_path))

    with pytest.raises(DocumentRegistrationError):
        service.list_histories(status="BAD")
    with pytest.raises(DocumentRegistrationError):
        service.list_histories(limit=0)


class FakeAnswerService:
    def __init__(self, response: AnswerResponse | None = None, error: AnswerGenerationError | None = None) -> None:
        self.response = response
        self.error = error

    def answer(self, question: str, mode: str = "hybrid") -> AnswerResponse:
        if self.error:
            raise self.error
        return self.response


class FakeDatabaseRepository:
    def health_check(self) -> bool:
        return True


def test_question_service_records_success_and_failures(tmp_path) -> None:
    history = HistoryService(_settings(tmp_path))
    question_service = QuestionService(
        FakeDatabaseRepository(),
        retrieval_service=None,
        answer_service=FakeAnswerService(response=_answer("leave")),
        history_service=history,
    )

    question_service.answer("leave")
    assert history.count() == 1

    failing_service = QuestionService(
        FakeDatabaseRepository(),
        retrieval_service=None,
        answer_service=FakeAnswerService(error=AnswerGenerationError("OLLAMA_TIMEOUT", "Timed out.")),
        history_service=history,
    )
    with pytest.raises(AnswerGenerationError):
        failing_service.answer("timeout")

    assert history.list_histories(status="FAILED").total_count == 1
