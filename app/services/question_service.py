from __future__ import annotations

import inspect

from app.models.document import AnswerResponse, SearchResponse
from app.repositories.database_repository import DatabaseRepository
from app.services.answer_service import AnswerService
from app.services.exceptions import AnswerGenerationError
from app.services.history_service import HistoryService
from app.services.retrieval_service import RetrievalService


class QuestionService:
    def __init__(
        self,
        database_repository: DatabaseRepository,
        retrieval_service: RetrievalService | None = None,
        answer_service: AnswerService | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        self._database_repository = database_repository
        self._retrieval_service = retrieval_service
        self._answer_service = answer_service
        self._history_service = history_service

    def status_message(self) -> str:
        if self._database_repository.health_check():
            return "인덱싱된 규정 청크를 키워드, 벡터, 하이브리드 모드로 검색합니다."
        return "데이터베이스 연결을 확인할 수 없습니다."

    def search(self, query: str, mode: str = "hybrid", include_archived: bool = False) -> SearchResponse:
        if self._retrieval_service is None:
            raise RuntimeError("검색 서비스가 연결되지 않았습니다.")
        return _call_search(self._retrieval_service, query, mode=mode, include_archived=include_archived)

    def answer(self, question: str, mode: str = "hybrid", include_archived: bool = False) -> AnswerResponse:
        if self._answer_service is None:
            raise RuntimeError("Answer service is not connected.")
        try:
            response = _call_answer(self._answer_service, question, mode=mode, include_archived=include_archived)
        except AnswerGenerationError as exc:
            if self._history_service is not None and question.strip():
                self._history_service.save_failure(question, mode, exc.code, exc.user_message)
            raise
        if self._history_service is not None:
            self._history_service.save_answer(response)
        return response


def _call_search(service, query: str, *, mode: str, include_archived: bool) -> SearchResponse:
    parameters = inspect.signature(service.search).parameters
    if "include_archived" in parameters:
        return service.search(query, mode=mode, include_archived=include_archived)
    return service.search(query, mode=mode)


def _call_answer(service, question: str, *, mode: str, include_archived: bool) -> AnswerResponse:
    parameters = inspect.signature(service.answer).parameters
    if "include_archived" in parameters:
        return service.answer(question, mode=mode, include_archived=include_archived)
    return service.answer(question, mode=mode)
