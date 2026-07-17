from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.models.document import Document
from app.services.document_extraction_service import DocumentExtractionService
from app.services.document_service import DocumentService
from app.services.exceptions import DocumentExtractionError, DocumentRegistrationError
from app.services.search_index_service import SearchIndexService


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


class DocumentExtractionWorker(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: DocumentExtractionService, document_id: str) -> None:
        super().__init__()
        self._service = service
        self._document_id = document_id

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(10, "문서 확인 중")
            self.progress.emit(35, "엑셀 시트 분석 중")
            result = self._service.extract_document(self._document_id)
            self.progress.emit(100, "완료")
            self.succeeded.emit(result)
        except DocumentExtractionError as exc:
            self.failed.emit(exc.user_message)
        except Exception:
            self.failed.emit("문서 내용을 추출하는 중 예상하지 못한 오류가 발생했습니다.")
        finally:
            self.finished.emit()


class SearchIndexWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: SearchIndexService, document_id: str, force: bool = False) -> None:
        super().__init__()
        self._service = service
        self._document_id = document_id
        self._force = force

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.index_document(self._document_id, force=self._force)
            self.succeeded.emit(result)
        except DocumentRegistrationError as exc:
            self.failed.emit(exc.user_message)
        except Exception:
            self.failed.emit("검색 인덱스를 생성하는 중 예상하지 못한 오류가 발생했습니다.")
        finally:
            self.finished.emit()


class DocumentViewModel(QObject):
    documents_changed = Signal(list)
    registration_started = Signal()
    registration_succeeded = Signal(object)
    registration_failed = Signal(str)
    registration_finished = Signal()
    extraction_started = Signal()
    extraction_progress = Signal(int, str)
    extraction_succeeded = Signal(object)
    extraction_failed = Signal(str)
    extraction_finished = Signal()
    indexing_started = Signal()
    indexing_succeeded = Signal(object)
    indexing_failed = Signal(str)
    indexing_finished = Signal()

    def __init__(
        self,
        service: DocumentService,
        extraction_service: DocumentExtractionService | None = None,
        search_index_service: SearchIndexService | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._extraction_service = extraction_service
        self._search_index_service = search_index_service
        self._thread: QThread | None = None
        self._worker: DocumentWorker | None = None
        self._extraction_thread: QThread | None = None
        self._extraction_worker: DocumentExtractionWorker | None = None
        self._indexing_thread: QThread | None = None
        self._indexing_worker: SearchIndexWorker | None = None

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

    def extract_document(self, document_id: str) -> bool:
        if self._extraction_service is None or self._extraction_thread is not None:
            return False

        self._extraction_thread = QThread()
        self._extraction_worker = DocumentExtractionWorker(self._extraction_service, document_id)
        self._extraction_worker.moveToThread(self._extraction_thread)
        self._extraction_thread.started.connect(self._extraction_worker.run)
        self._extraction_worker.progress.connect(self.extraction_progress)
        self._extraction_worker.succeeded.connect(self._handle_extraction_success)
        self._extraction_worker.failed.connect(self.extraction_failed)
        self._extraction_worker.finished.connect(self._extraction_thread.quit)
        self._extraction_worker.finished.connect(self._extraction_worker.deleteLater)
        self._extraction_thread.finished.connect(self._extraction_thread.deleteLater)
        self._extraction_thread.finished.connect(self._clear_extraction_worker)

        self.extraction_started.emit()
        self._extraction_thread.start()
        return True

    def index_document(self, document_id: str, force: bool = False) -> bool:
        if self._search_index_service is None or self._indexing_thread is not None:
            return False

        self._indexing_thread = QThread()
        self._indexing_worker = SearchIndexWorker(self._search_index_service, document_id, force)
        self._indexing_worker.moveToThread(self._indexing_thread)
        self._indexing_thread.started.connect(self._indexing_worker.run)
        self._indexing_worker.succeeded.connect(self._handle_indexing_success)
        self._indexing_worker.failed.connect(self.indexing_failed)
        self._indexing_worker.finished.connect(self._indexing_thread.quit)
        self._indexing_worker.finished.connect(self._indexing_worker.deleteLater)
        self._indexing_thread.finished.connect(self._indexing_thread.deleteLater)
        self._indexing_thread.finished.connect(self._clear_indexing_worker)

        self.indexing_started.emit()
        self._indexing_thread.start()
        return True

    def load_chunks(self, document_id: str):
        if self._extraction_service is None:
            return []
        return self._extraction_service.list_chunks(document_id)

    def load_sheets(self, document_id: str):
        if self._extraction_service is None:
            return []
        return self._extraction_service.list_sheets(document_id)

    def extraction_counts(self, document_id: str) -> tuple[int, int, int]:
        if self._extraction_service is None:
            return 0, 0, 0
        return self._extraction_service.counts_by_document(document_id)

    @Slot(object)
    def _handle_success(self, document: Document) -> None:
        self.registration_succeeded.emit(document)
        self.load_documents()

    @Slot(object)
    def _handle_extraction_success(self, result) -> None:
        self.extraction_succeeded.emit(result)
        self.load_documents()

    @Slot(object)
    def _handle_indexing_success(self, result) -> None:
        self.indexing_succeeded.emit(result)
        self.load_documents()

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.registration_finished.emit()

    @Slot()
    def _clear_extraction_worker(self) -> None:
        self._extraction_thread = None
        self._extraction_worker = None
        self.extraction_finished.emit()

    @Slot()
    def _clear_indexing_worker(self) -> None:
        self._indexing_thread = None
        self._indexing_worker = None
        self.indexing_finished.emit()
