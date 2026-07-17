from __future__ import annotations

import uuid
from datetime import date, datetime

from app.config.settings import Settings
from app.models.document import AnswerResponse, HistoryFilters, HistoryListResult, HistorySource, QuestionHistory, VerifiedSource
from app.repositories.history_repository import HistoryRepository
from app.services.exceptions import DocumentRegistrationError


VALID_STATUSES = {"SUCCESS", "INSUFFICIENT_EVIDENCE", "NO_EVIDENCE", "FAILED"}


class HistoryService:
    def __init__(self, settings: Settings, repository: HistoryRepository | None = None) -> None:
        self._settings = settings
        self._repository = repository or HistoryRepository(settings.database_path)

    def save_answer(self, response: AnswerResponse) -> QuestionHistory:
        if not response.question.strip():
            raise DocumentRegistrationError("Question history cannot store an empty question.")
        now = datetime.now().replace(microsecond=0)
        history_id = _new_id("HIST")
        status = _status_for_response(response)
        history = QuestionHistory(
            history_id=history_id,
            request_id=_new_id("REQ"),
            question=response.question,
            answer=response.answer,
            status=status,
            insufficient_evidence=response.insufficient_evidence,
            error_code=response.error_code,
            error_message=response.reason if response.error_code else None,
            search_mode=response.retrieval.mode,
            requested_top_k=response.retrieval.requested_top_k,
            retrieved_count=len(response.retrieval.results),
            used_evidence_count=len(response.verified_sources),
            ollama_model=self._settings.ollama_model,
            total_duration_ms=response.elapsed_time_ms,
            retrieval_duration_ms=response.retrieval.elapsed_time_ms,
            generation_duration_ms=max(0, response.elapsed_time_ms - response.retrieval.elapsed_time_ms),
            created_at=now,
            sources=_sources_for_history(history_id, response.verified_sources, now),
        )
        self._repository.save(history)
        return history

    def save_failure(
        self,
        question: str,
        search_mode: str,
        error_code: str,
        error_message: str,
        total_duration_ms: int = 0,
    ) -> QuestionHistory:
        cleaned = " ".join(question.strip().split())
        if not cleaned:
            raise DocumentRegistrationError("Question history cannot store an empty question.")
        now = datetime.now().replace(microsecond=0)
        history = QuestionHistory(
            history_id=_new_id("HIST"),
            request_id=_new_id("REQ"),
            question=cleaned,
            answer="",
            status="FAILED",
            insufficient_evidence=False,
            error_code=error_code,
            error_message=error_message,
            search_mode=search_mode,
            requested_top_k=self._settings.retrieval_top_k,
            retrieved_count=0,
            used_evidence_count=0,
            ollama_model=self._settings.ollama_model,
            total_duration_ms=total_duration_ms,
            retrieval_duration_ms=0,
            generation_duration_ms=0,
            created_at=now,
            sources=(),
        )
        self._repository.save(history)
        return history

    def list_histories(
        self,
        search_text: str | None = None,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> HistoryListResult:
        if status and status not in VALID_STATUSES:
            raise DocumentRegistrationError("Invalid history status filter.")
        if limit <= 0 or limit > 200 or offset < 0:
            raise DocumentRegistrationError("Invalid history pagination.")
        if start_date and end_date and start_date > end_date:
            raise DocumentRegistrationError("Invalid history date range.")
        filters = HistoryFilters(
            search_text=" ".join(search_text.strip().split()) if search_text else None,
            status=status or None,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return self._repository.list(filters)

    def get_history(self, history_id: str) -> QuestionHistory:
        history = self._repository.get(history_id)
        if history is None:
            raise DocumentRegistrationError("Question history was not found.")
        return history

    def delete_history(self, history_id: str) -> bool:
        return self._repository.delete(history_id)

    def delete_all(self) -> int:
        return self._repository.delete_all()

    def count(self) -> int:
        return self._repository.count()


def _status_for_response(response: AnswerResponse) -> str:
    if response.error_code == "NO_EVIDENCE":
        return "NO_EVIDENCE"
    if response.insufficient_evidence:
        return "INSUFFICIENT_EVIDENCE"
    if not response.generation_succeeded:
        return "FAILED"
    return "SUCCESS"


def _sources_for_history(history_id: str, sources: list[VerifiedSource], created_at: datetime) -> tuple[HistorySource, ...]:
    seen: set[str] = set()
    result: list[HistorySource] = []
    for source in sources:
        if source.chunk_id in seen:
            continue
        seen.add(source.chunk_id)
        result.append(
            HistorySource(
                history_source_id=_new_id("HSRC"),
                history_id=history_id,
                evidence_id=source.evidence_id,
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                sheet_id=None,
                source_rank=len(result) + 1,
                document_display_name=source.original_name,
                sheet_name=source.sheet_name,
                article=source.article,
                title=source.title,
                cell_range=source.cell_range,
                cell_refs=source.cell_refs,
                content=source.content,
                created_at=created_at,
            )
        )
    return tuple(result)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"
