from __future__ import annotations

from datetime import datetime

import pytest

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository


def _document(document_id: str, file_hash: str, uploaded_at: datetime) -> Document:
    return Document(
        id=document_id,
        original_name=f"{document_id}.xlsx",
        stored_path=f"uploads/{document_id}/document.xlsx",
        file_hash=file_hash,
        file_size_bytes=100,
        version=None,
        effective_date=None,
        revised_date=None,
        department=None,
        is_latest=True,
        status="UPLOADED",
        error_message=None,
        uploaded_at=uploaded_at,
    )


def test_create_and_get_by_id(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    document = _document("DOC-1", "hash-1", datetime(2026, 1, 1, 10, 0, 0))

    repository.create(document)

    assert repository.get_by_id("DOC-1") == document


def test_get_by_hash(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    document = _document("DOC-1", "hash-1", datetime(2026, 1, 1, 10, 0, 0))

    repository.create(document)

    assert repository.get_by_hash("hash-1") == document


def test_list_all_latest_first(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    older = _document("DOC-1", "hash-1", datetime(2026, 1, 1, 10, 0, 0))
    newer = _document("DOC-2", "hash-2", datetime(2026, 1, 2, 10, 0, 0))

    repository.create(older)
    repository.create(newer)

    assert repository.list_all() == [newer, older]


def test_duplicate_hash_blocked(tmp_path) -> None:
    repository = DocumentRepository(tmp_path / "db" / "app.sqlite3")
    repository.create(_document("DOC-1", "same-hash", datetime(2026, 1, 1, 10, 0, 0)))

    with pytest.raises(Exception):
        repository.create(_document("DOC-2", "same-hash", datetime(2026, 1, 2, 10, 0, 0)))

