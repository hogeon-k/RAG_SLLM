from __future__ import annotations

from app.models.document import AnswerResponse, SearchResponse
from app.viewmodels.question_viewmodel import QuestionViewModel


class DummyQuestionService:
    def status_message(self) -> str:
        return "ok"


def _response() -> AnswerResponse:
    retrieval = SearchResponse("q", "hybrid", [], 5, 0, 0, 0, tuple())
    return AnswerResponse(
        question="q",
        answer="a",
        insufficient_evidence=False,
        reason="",
        used_evidence=[],
        verified_sources=[],
        retrieval=retrieval,
        generation_succeeded=True,
        elapsed_time_ms=1,
    )


def test_question_viewmodel_ignores_stale_success(qtbot) -> None:
    view_model = QuestionViewModel(DummyQuestionService())
    received: list[AnswerResponse] = []
    view_model.answer_succeeded.connect(received.append)
    view_model._active_request_id = "REQ-B"

    view_model._handle_success("REQ-A", _response())
    view_model._handle_success("REQ-B", _response())

    assert len(received) == 1


def test_question_viewmodel_ignores_stale_failure(qtbot) -> None:
    view_model = QuestionViewModel(DummyQuestionService())
    received: list[str] = []
    view_model.answer_failed.connect(received.append)
    view_model._active_request_id = "REQ-B"

    view_model._handle_failure("REQ-A", "old")
    view_model._handle_failure("REQ-B", "new")

    assert received == ["new"]
