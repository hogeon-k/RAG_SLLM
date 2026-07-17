from __future__ import annotations

from datetime import datetime

from app.models.document import Document, DocumentChunk, ParsedCell, ParsedSheet
from app.repositories.document_repository import DocumentRepository
from app.repositories.extraction_repository import ExtractionRepository


def _document(document_id: str) -> Document:
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
        status="UPLOADED",
        error_message=None,
        uploaded_at=datetime(2026, 1, 1, 10, 0, 0),
    )


def _extraction(document_id: str, text: str):
    sheet = ParsedSheet(f"{document_id}-S001", document_id, "규정", 0, "visible", 1, 1, 1, 0, datetime(2026, 1, 1))
    cell = ParsedCell(f"{sheet.id}-A1", document_id, sheet.id, "규정", "A1", 1, 1, "string", text, None, None, None, False, False)
    chunk = DocumentChunk(
        f"{sheet.id}-C0000",
        document_id,
        sheet.id,
        "규정",
        "A1",
        "A1",
        "A1:A1",
        ("A1",),
        1,
        1,
        None,
        None,
        None,
        None,
        text,
        0,
        "hash",
        datetime(2026, 1, 1),
    )
    return [sheet], [cell], [chunk]


def test_replace_extraction_stores_and_replaces(tmp_path) -> None:
    db = tmp_path / "db.sqlite3"
    DocumentRepository(db).create(_document("DOC-1"))
    repository = ExtractionRepository(db)

    repository.replace_extraction("DOC-1", *_extraction("DOC-1", "첫번째"))
    repository.replace_extraction("DOC-1", *_extraction("DOC-1", "두번째"))

    chunks = repository.list_chunks("DOC-1")
    assert len(chunks) == 1
    assert chunks[0].content == "두번째"
    assert repository.count_cells("DOC-1") == 1
    assert repository.count_chunks("DOC-1") == 1


def test_extraction_is_document_scoped(tmp_path) -> None:
    db = tmp_path / "db.sqlite3"
    documents = DocumentRepository(db)
    documents.create(_document("DOC-1"))
    documents.create(_document("DOC-2"))
    repository = ExtractionRepository(db)

    repository.replace_extraction("DOC-1", *_extraction("DOC-1", "문서1"))
    repository.replace_extraction("DOC-2", *_extraction("DOC-2", "문서2"))

    assert repository.list_chunks("DOC-1")[0].content == "문서1"
    assert repository.list_chunks("DOC-2")[0].content == "문서2"

