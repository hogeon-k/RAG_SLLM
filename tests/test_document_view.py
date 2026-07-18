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
            indexing_started = Signal()
            indexing_succeeded = Signal(object)
            indexing_failed = Signal(str)
            indexing_finished = Signal()
            lifecycle_changed = Signal(object)
            lifecycle_failed = Signal(str)
            document_deletion_started = Signal()
            document_deletion_succeeded = Signal(object)
            document_deletion_failed = Signal(str)
            document_deletion_finished = Signal()

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
        self.indexing_started = self._signals.indexing_started
        self.indexing_succeeded = self._signals.indexing_succeeded
        self.indexing_failed = self._signals.indexing_failed
        self.indexing_finished = self._signals.indexing_finished
        self.lifecycle_changed = self._signals.lifecycle_changed
        self.lifecycle_failed = self._signals.lifecycle_failed
        self.document_deletion_started = self._signals.document_deletion_started
        self.document_deletion_succeeded = self._signals.document_deletion_succeeded
        self.document_deletion_failed = self._signals.document_deletion_failed
        self.document_deletion_finished = self._signals.document_deletion_finished
        self._documents = documents or []
        self.lifecycle_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []

    def load_documents(self):
        self.documents_changed.emit(self._documents)
        return self._documents

    def register_document(self, *args, **kwargs) -> bool:
        return True

    def extract_document(self, *args, **kwargs) -> bool:
        return True

    def index_document(self, *args, **kwargs) -> bool:
        return True

    def set_lifecycle_status(self, document_id, lifecycle_status) -> bool:
        self.lifecycle_calls.append((document_id, lifecycle_status))
        return True

    def promote_current(self, document_id) -> bool:
        self.lifecycle_calls.append((document_id, "CURRENT"))
        return True

    def delete_document(self, document_id) -> bool:
        self.delete_calls.append(document_id)
        return True

    def load_chunks(self, document_id):
        return []

    def load_sheets(self, document_id):
        return []

    def extraction_counts(self, document_id):
        return 0, 0, 0


def _document(status: str = "UPLOADED", lifecycle_status: str = "CURRENT") -> Document:
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
        status=status,
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
        lifecycle_status=lifecycle_status,
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
    assert view.table.item(0, 12).text() == "CURRENT"


def test_document_view_reenables_button_after_failure(qtbot) -> None:
    model = FakeDocumentViewModel()
    view = DocumentView(model)
    qtbot.addWidget(view)

    view._on_registration_started()
    view._on_registration_finished()

    assert view.register_button.isEnabled()


def test_document_view_index_buttons_follow_document_status(qtbot) -> None:
    view = DocumentView(FakeDocumentViewModel([_document("UPLOADED")]))
    qtbot.addWidget(view)

    view.table.selectRow(0)
    assert not view.index_button.isEnabled()
    assert not view.reindex_button.isEnabled()


def test_document_view_keeps_index_buttons_disabled_while_busy(qtbot) -> None:
    model = FakeDocumentViewModel([_document("PARSED")])
    view = DocumentView(model)
    qtbot.addWidget(view)
    view.table.selectRow(0)

    assert view.index_button.isEnabled()

    view._on_indexing_started()
    model._documents = [_document("COMPLETED")]
    view._render_documents(model._documents)

    assert not view.index_button.isEnabled()
    assert not view.reindex_button.isEnabled()

    view._on_indexing_finished()

    assert not view.index_button.isEnabled()
    assert view.reindex_button.isEnabled()

    view._render_documents([_document("PARSED")])
    view.table.selectRow(0)
    assert view.index_button.isEnabled()
    assert not view.reindex_button.isEnabled()

    view._render_documents([_document("COMPLETED")])
    view.table.selectRow(0)
    assert not view.index_button.isEnabled()
    assert view.reindex_button.isEnabled()

    view._render_documents([_document("INDEXING")])
    view.table.selectRow(0)
    assert not view.index_button.isEnabled()
    assert not view.reindex_button.isEnabled()

    view._render_documents([_document("FAILED")])
    view.table.selectRow(0)
    assert not view.index_button.isEnabled()
    assert not view.reindex_button.isEnabled()


def test_document_view_lifecycle_buttons_follow_status(qtbot) -> None:
    view = DocumentView(FakeDocumentViewModel([_document("COMPLETED", "CURRENT")]))
    qtbot.addWidget(view)
    view.table.selectRow(0)

    assert not view.current_button.isEnabled()
    assert view.archive_button.isEnabled()

    view._render_documents([_document("COMPLETED", "ARCHIVED")])
    view.table.selectRow(0)

    assert view.current_button.isEnabled()
    assert not view.archive_button.isEnabled()

    view._render_documents([_document("INDEXING", "CURRENT")])
    view.table.selectRow(0)

    assert not view.current_button.isEnabled()
    assert not view.archive_button.isEnabled()


def test_document_view_delete_button_follows_document_status(qtbot) -> None:
    view = DocumentView(FakeDocumentViewModel([_document("COMPLETED")]))
    qtbot.addWidget(view)
    view.table.selectRow(0)

    assert view.delete_button.isEnabled()

    view._render_documents([_document("INDEXING")])
    view.table.selectRow(0)

    assert not view.delete_button.isEnabled()


def test_document_view_delete_confirmation_calls_view_model(qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    model = FakeDocumentViewModel([_document("COMPLETED")])
    view = DocumentView(model)
    qtbot.addWidget(view)
    view.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

    view._delete_selected_document()

    assert model.delete_calls == ["DOC-1"]
    assert not view.delete_button.isEnabled()
