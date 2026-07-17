from __future__ import annotations

from app.repositories.database_repository import DatabaseRepository


class QuestionService:
    def __init__(self, database_repository: DatabaseRepository) -> None:
        self._database_repository = database_repository

    def status_message(self) -> str:
        if self._database_repository.health_check():
            return "업로드한 규정에 대해 질문하는 화면입니다."
        return "데이터베이스 연결을 확인할 수 없습니다."

