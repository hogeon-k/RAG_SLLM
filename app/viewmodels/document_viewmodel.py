from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.models.document import Document
from app.services.document_service import DocumentService
from app.services.exceptions import DocumentRegistrationError


class DocumentWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        service: DocumentService,
        source_path: Path,
        version: str | None,
        effective_date: date | None,
        revised_date: date | None,
        department: str | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._source_path = source_path
        self._version = version
        self._effective_date = effective_date
        self._revised_date = revised_date
        self._department = department

    @Slot()
    def run(self) -> None:
        try:
            document = self._service.register_document(
                self._source_path,
                version=self._version,
                effective_date=self._effective_date,
                revised_date=self._revised_date,
                department=self._department,
            )
            self.succeeded.emit(document)
        except DocumentRegistrationError as exc:
            self.failed.emit(exc.user_message)
        except Exception:
            self.failed.emit("문서를 등록하는 중 예상하지 못한 오류가 발생했습니다.")
        finally:
            self.finished.emit()


class DocumentViewModel(QObject):
    documents_changed = Signal(list)
    registration_started = Signal()
    registration_succeeded = Signal(object)
    registration_failed = Signal(str)
    registration_finished = Signal()

    def __init__(self, service: DocumentService) -> None:
        super().__init__()
        self._service = service
        self._thread: QThread | None = None
        self._worker: DocumentWorker | None = None

    def description(self) -> str:
        return self._service.status_message()

    def load_documents(self) -> list[Document]:
        documents = self._service.list_documents()
        self.documents_changed.emit(documents)
        return documents

    def register_document(
        self,
        source_path: Path,
        version: str | None = None,
        effective_date: date | None = None,
        revised_date: date | None = None,
        department: str | None = None,
    ) -> bool:
        if self._thread is not None:
            return False

        self._thread = QThread()
        self._worker = DocumentWorker(
            self._service,
            source_path,
            version,
            effective_date,
            revised_date,
            department,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._handle_success)
        self._worker.failed.connect(self.registration_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)

        self.registration_started.emit()
        self._thread.start()
        return True

    @Slot(object)
    def _handle_success(self, document: Document) -> None:
        self.registration_succeeded.emit(document)
        self.load_documents()

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.registration_finished.emit()
