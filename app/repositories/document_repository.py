from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.schema import initialize_database
from app.models.document import Document


class DocumentRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        initialize_database(database_path)

    def create(self, document: Document) -> Document:
        with open_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, original_name, stored_path, file_hash, file_size_bytes,
                    version, effective_date, revised_date, department,
                    is_latest, status, error_message, uploaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.original_name,
                    document.stored_path,
                    document.file_hash,
                    document.file_size_bytes,
                    document.version,
                    _date_to_db(document.effective_date),
                    _date_to_db(document.revised_date),
                    document.department,
                    1 if document.is_latest else 0,
                    document.status,
                    document.error_message,
                    document.uploaded_at.isoformat(timespec="seconds"),
                ),
            )
        return document

    def get_by_id(self, document_id: str) -> Document | None:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return _row_to_document(row) if row else None

    def get_by_hash(self, file_hash: str) -> Document | None:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
        return _row_to_document(row) if row else None

    def list_all(self) -> list[Document]:
        with open_connection(self._database_path) as connection:
            rows = connection.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
        return [_row_to_document(row) for row in rows]

    def count(self) -> int:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0])

    def update_parse_status(
        self,
        document_id: str,
        status: str,
        parsed_at: datetime | None = None,
        parse_error: str | None = None,
    ) -> None:
        with open_connection(self._database_path) as connection:
            connection.execute(
                """
                UPDATE documents
                SET status = ?, parsed_at = ?, parse_error = ?
                WHERE id = ?
                """,
                (
                    status,
                    parsed_at.isoformat(timespec="seconds") if parsed_at else None,
                    parse_error,
                    document_id,
                ),
            )


def _date_to_db(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date_from_db(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _row_to_document(row) -> Document:
    return Document(
        id=row["id"],
        original_name=row["original_name"],
        stored_path=row["stored_path"],
        file_hash=row["file_hash"],
        file_size_bytes=row["file_size_bytes"],
        version=row["version"],
        effective_date=_date_from_db(row["effective_date"]),
        revised_date=_date_from_db(row["revised_date"]),
        department=row["department"],
        is_latest=bool(row["is_latest"]),
        status=row["status"],
        error_message=row["error_message"],
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
        parsed_at=datetime.fromisoformat(row["parsed_at"]) if "parsed_at" in row.keys() and row["parsed_at"] else None,
        parse_error=row["parse_error"] if "parse_error" in row.keys() else None,
    )
