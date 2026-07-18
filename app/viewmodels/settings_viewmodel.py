from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.config.settings import Settings
from app.repositories.database_repository import DatabaseRepository
from app.services.embedding_service import EmbeddingService
from app.services.ollama_client import OllamaClient


class SettingsStatusWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, settings: Settings, database_repository: DatabaseRepository) -> None:
        super().__init__()
        self._settings = settings
        self._database = database_repository

    @Slot()
    def run(self) -> None:
        try:
            ollama_status = OllamaClient(self._settings).check_status()
            self.succeeded.emit(
                {
                    "sqlite_ok": self._database.health_check(),
                    "chroma_ready": self._settings.vector_db_dir.exists(),
                    "server_available": ollama_status.server_available,
                    "model_available": ollama_status.model_available,
                    "embedding_status": EmbeddingService(
                        self._settings.embedding_model,
                        self._settings.embedding_device,
                        self._settings.embedding_batch_size,
                    ).get_status(),
                    "message": ollama_status.message,
                }
            )
        except Exception:
            self.failed.emit("System status check failed.")
        finally:
            self.finished.emit()


class SettingsViewModel(QObject):
    status_started = Signal()
    status_succeeded = Signal(object)
    status_failed = Signal(str)
    status_finished = Signal()

    def __init__(self, settings: Settings, database_repository: DatabaseRepository) -> None:
        super().__init__()
        self._settings = settings
        self._database_repository = database_repository
        self._thread: QThread | None = None
        self._worker: SettingsStatusWorker | None = None

    def check_status(self) -> bool:
        if self._thread is not None:
            return False
        self._thread = QThread()
        self._worker = SettingsStatusWorker(self._settings, self._database_repository)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self.status_succeeded)
        self._worker.failed.connect(self.status_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self.status_started.emit()
        self._thread.start()
        return True

    def shutdown(self, timeout_ms: int = 1500) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            self._thread.wait(timeout_ms)

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.status_finished.emit()
