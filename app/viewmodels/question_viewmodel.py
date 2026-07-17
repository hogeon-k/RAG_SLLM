from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.models.document import AnswerResponse, SearchResponse
from app.services.exceptions import AnswerGenerationError, DocumentRegistrationError
from app.services.question_service import QuestionService


class QuestionWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: QuestionService, question: str, mode: str) -> None:
        super().__init__()
        self._service = service
        self._question = question
        self._mode = mode

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._service.answer(self._question, self._mode))
        except AnswerGenerationError as exc:
            self.failed.emit(exc.user_message)
        except DocumentRegistrationError as exc:
            self.failed.emit(exc.user_message)
        except Exception:
            self.failed.emit("Answer generation failed.")
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

    def description(self) -> str:
        return self._service.status_message()

    def search(self, query: str, mode: str = "hybrid") -> SearchResponse:
        return self._service.search(query, mode)

    def answer(self, query: str, mode: str = "hybrid") -> AnswerResponse:
        return self._service.answer(query, mode)

    def start_answer(self, query: str, mode: str = "hybrid") -> bool:
        if self._thread is not None:
            return False
        self._thread = QThread()
        self._worker = QuestionWorker(self._service, query, mode)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self.answer_succeeded)
        self._worker.failed.connect(self.answer_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self.answer_started.emit()
        self._thread.start()
        return True

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.answer_finished.emit()
