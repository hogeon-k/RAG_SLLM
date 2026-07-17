from __future__ import annotations

from app.models.document import AnswerResponse, SearchResponse
from app.repositories.database_repository import DatabaseRepository
from app.services.answer_service import AnswerService
from app.services.retrieval_service import RetrievalService


class QuestionService:
    def __init__(
        self,
        database_repository: DatabaseRepository,
        retrieval_service: RetrievalService | None = None,
        answer_service: AnswerService | None = None,
    ) -> None:
        self._database_repository = database_repository
        self._retrieval_service = retrieval_service
        self._answer_service = answer_service

    def status_message(self) -> str:
        if self._database_repository.health_check():
            return "인덱싱된 규정 청크를 키워드, 벡터, 하이브리드 모드로 검색합니다."
        return "데이터베이스 연결을 확인할 수 없습니다."

    def search(self, query: str, mode: str = "hybrid") -> SearchResponse:
        if self._retrieval_service is None:
            raise RuntimeError("검색 서비스가 연결되지 않았습니다.")
        return self._retrieval_service.search(query, mode=mode)

    def answer(self, question: str, mode: str = "hybrid") -> AnswerResponse:
        if self._answer_service is None:
            raise RuntimeError("Answer service is not connected.")
        return self._answer_service.answer(question, mode=mode)
