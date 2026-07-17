from __future__ import annotations

from datetime import datetime

from app.models.document import Document
from app.views.document_view import DocumentView


class FakeDocumentViewModel:
    def __init__(self, documents=None) -> None:
        from PySide6.QtCore import QObject, Signal

        class Signals(QObject):
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

        self._signals = Signals()
        self.documents_changed = self._signals.documents_changed
        self.registration_started = self._signals.registration_started
        self.registration_succeeded = self._signals.registration_succeeded
        self.registration_failed = self._signals.registration_failed
        self.registration_finished = self._signals.registration_finished
        self.extraction_started = self._signals.extraction_started
        self.extraction_progress = self._signals.extraction_progress
        self.extraction_succeeded = self._signals.extraction_succeeded
        self.extraction_failed = self._signals.extraction_failed
        self.extraction_finished = self._signals.extraction_finished
        self._documents = documents or []

    def load_documents(self):
        self.documents_changed.emit(self._documents)
        return self._documents

    def register_document(self, *args, **kwargs) -> bool:
        return True

    def extract_document(self, *args, **kwargs) -> bool:
        return True

    def load_chunks(self, document_id):
        return []

    def load_sheets(self, document_id):
        return []

    def extraction_counts(self, document_id):
        return 0, 0, 0


def _document() -> Document:
    return Document(
        id="DOC-1",
        original_name="rules.xlsx",
        stored_path="uploads/DOC-1/document.xlsx",
        file_hash="hash",
        file_size_bytes=2048,
        version=None,
        effective_date=None,
        revised_date=None,
        department=None,
        is_latest=True,
        status="UPLOADED",
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
    )


def test_document_view_shows_empty_message(qtbot) -> None:
    view = DocumentView(FakeDocumentViewModel())
    qtbot.addWidget(view)

    assert not view.empty_label.isHidden()
    assert view.table.isHidden()


def test_document_view_renders_documents(qtbot) -> None:
    view = DocumentView(FakeDocumentViewModel([_document()]))
    qtbot.addWidget(view)

    assert not view.table.isHidden()
    assert view.empty_label.isHidden()
    assert view.table.item(0, 0).text() == "rules.xlsx"
    assert view.table.item(0, 1).text() == "미입력"
    assert view.table.item(0, 7).text() == "등록 완료"


def test_document_view_reenables_button_after_failure(qtbot) -> None:
    model = FakeDocumentViewModel()
    view = DocumentView(model)
    qtbot.addWidget(view)

    view._on_registration_started()
    view._on_registration_finished()

    assert view.register_button.isEnabled()
