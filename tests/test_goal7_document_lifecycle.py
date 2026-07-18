from __future__ import annotations

from datetime import datetime

import pytest

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.repositories.search_index_repository import SearchIndexRepository
from app.services.document_service import DocumentService
from app.services.exceptions import DocumentRegistrationError


def _document(document_id: str, status: str = "COMPLETED", lifecycle_status: str = "CURRENT", family: str | None = None) -> Document:
    return Document(
        id=document_id,
        original_name=f"{document_id}.xlsx",
        stored_path=f"uploads/{document_id}/document.xlsx",
        file_hash=f"hash-{document_id}",
        file_size_bytes=100,
        version=None,
        effective_date=None,
        revised_date=None,
        department=None,
        is_latest=True,
        status=status,
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
        lifecycle_status=lifecycle_status,
        document_family=family,
    )


def test_existing_document_defaults_to_current(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    repository.create(_document("DOC-1"))

    document = repository.get_by_id("DOC-1")

    assert document is not None
    assert document.lifecycle_status == "CURRENT"


def test_ready_document_ids_exclude_archived_and_non_completed_by_default(tmp_path) -> None:
    database_path = tmp_path / "db" / "app.sqlite3"
    documents = DocumentRepository(database_path)
    indexes = SearchIndexRepository(database_path)
    documents.create(_document("DOC-CURRENT", status="COMPLETED", lifecycle_status="CURRENT"))
    documents.create(_document("DOC-ARCHIVED", status="COMPLETED", lifecycle_status="ARCHIVED"))
    documents.create(_document("DOC-STALE", status="PARSED", lifecycle_status="CURRENT"))
    for document_id in ("DOC-CURRENT", "DOC-ARCHIVED", "DOC-STALE"):
        indexes.upsert_status(document_id, "READY")

    assert indexes.ready_document_ids() == ["DOC-CURRENT"]
    assert indexes.ready_document_ids(include_archived=True) == ["DOC-CURRENT", "DOC-ARCHIVED"]


def test_promote_current_archives_same_family_transactionally(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    repository.create(_document("DOC-OLD", family="policy"))
    repository.create(_document("DOC-NEW", lifecycle_status="ARCHIVED", family="policy"))

    archived_ids = repository.promote_current("DOC-NEW")

    assert archived_ids == ["DOC-OLD"]
    assert repository.get_by_id("DOC-NEW").lifecycle_status == "CURRENT"
    assert repository.get_by_id("DOC-OLD").lifecycle_status == "ARCHIVED"


def test_document_service_blocks_lifecycle_change_while_processing(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    repository.create(_document("DOC-1", status="INDEXING"))
    service = DocumentService.__new__(DocumentService)
    service._repository = repository

    with pytest.raises(DocumentRegistrationError):
        service.set_lifecycle_status("DOC-1", "ARCHIVED")
