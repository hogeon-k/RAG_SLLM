from __future__ import annotations

import uuid

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.models.document import AnswerResponse, SearchResponse
from app.services.exceptions import AnswerGenerationError, DocumentRegistrationError
from app.services.question_service import QuestionService


class QuestionWorker(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, request_id: str, service: QuestionService, question: str, mode: str, include_archived: bool) -> None:
        super().__init__()
        self.request_id = request_id
        self._service = service
        self._question = question
        self._mode = mode
        self._include_archived = include_archived

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self.request_id, self._service.answer(self._question, self._mode, include_archived=self._include_archived))
        except AnswerGenerationError as exc:
            self.failed.emit(self.request_id, exc.user_message)
        except DocumentRegistrationError as exc:
            self.failed.emit(self.request_id, exc.user_message)
        except Exception:
            self.failed.emit(self.request_id, "Answer generation failed.")
        finally:
            self.finished.emit()


class QuestionViewModel(QObject):
    answer_started = Signal()
    answer_succeeded = Signal(object)
    answer_failed = Signal(str)
    answer_finished = Signal()

    def __init__(self, service: QuestionService) -> None:
        super().__init__()
        self._service = service
        self._thread: QThread | None = None
        self._worker: QuestionWorker | None = None
        self._active_request_id: str | None = None

    def description(self) -> str:
        return self._service.status_message()

    def search(self, query: str, mode: str = "hybrid", include_archived: bool = False) -> SearchResponse:
        return self._service.search(query, mode, include_archived=include_archived)

    def answer(self, query: str, mode: str = "hybrid", include_archived: bool = False) -> AnswerResponse:
        return self._service.answer(query, mode, include_archived=include_archived)

    def start_answer(self, query: str, mode: str = "hybrid", include_archived: bool = False) -> bool:
        if self._thread is not None:
            return False
        request_id = f"REQ-{uuid.uuid4()}"
        self._active_request_id = request_id
        self._thread = QThread()
        self._worker = QuestionWorker(request_id, self._service, query, mode, include_archived)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._handle_success)
        self._worker.failed.connect(self._handle_failure)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self.answer_started.emit()
        self._thread.start()
        return True

    def cancel_active_request(self) -> None:
        self._active_request_id = None
        if self._thread is not None:
            self._thread.requestInterruption()

    def shutdown(self, timeout_ms: int = 1500) -> None:
        self.cancel_active_request()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(timeout_ms)

    @Slot(str, object)
    def _handle_success(self, request_id: str, response: AnswerResponse) -> None:
        if request_id != self._active_request_id:
            return
        self.answer_succeeded.emit(response)

    @Slot(str, str)
    def _handle_failure(self, request_id: str, message: str) -> None:
        if request_id != self._active_request_id:
            return
        self.answer_failed.emit(message)

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self._active_request_id = None
        self.answer_finished.emit()
