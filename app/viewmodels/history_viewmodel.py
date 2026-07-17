from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.services.exceptions import DocumentRegistrationError
from app.services.history_service import HistoryService


class HistoryWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, action, *args) -> None:
        super().__init__()
        self._action = action
        self._args = args

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._action(*self._args))
        except DocumentRegistrationError as exc:
            self.failed.emit(exc.user_message)
        except Exception:
            self.failed.emit("Question history operation failed.")
        finally:
            self.finished.emit()


class HistoryViewModel(QObject):
    operation_started = Signal()
    list_succeeded = Signal(object)
    detail_succeeded = Signal(object)
    delete_succeeded = Signal(object)
    operation_failed = Signal(str)
    operation_finished = Signal()

    def __init__(self, service: HistoryService) -> None:
        super().__init__()
        self._service = service
        self._thread: QThread | None = None
        self._worker: HistoryWorker | None = None

    def load_histories(self, search_text: str = "", status: str = "", limit: int = 50, offset: int = 0) -> bool:
        return self._start(self._service.list_histories, search_text or None, status or None, None, None, limit, offset, self.list_succeeded)

    def load_detail(self, history_id: str) -> bool:
        return self._start(self._service.get_history, history_id, self.detail_succeeded)

    def delete_history(self, history_id: str) -> bool:
        return self._start(self._delete_one, history_id, self.delete_succeeded)

    def delete_all(self) -> bool:
        return self._start(self._service.delete_all, self.delete_succeeded)

    def _delete_one(self, history_id: str) -> int:
        return 1 if self._service.delete_history(history_id) else 0

    def _start(self, action, *args) -> bool:
        if self._thread is not None:
            return False
        signal = args[-1]
        action_args = args[:-1]
        self._thread = QThread()
        self._worker = HistoryWorker(action, *action_args)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(signal)
        self._worker.failed.connect(self.operation_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self.operation_started.emit()
        self._thread.start()
        return True

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.operation_finished.emit()
