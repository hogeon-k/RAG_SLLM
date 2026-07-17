from __future__ import annotations

from app.services.question_service import QuestionService


class QuestionViewModel:
    def __init__(self, service: QuestionService) -> None:
        self._service = service

    def description(self) -> str:
        return self._service.status_message()

