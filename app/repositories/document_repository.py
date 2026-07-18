from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.schema import initialize_database
from app.models.document import Document, DocumentDeleteResult


class DocumentRepository:
    VALID_LIFECYCLE_STATUSES = {"CURRENT", "ARCHIVED"}

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
                    is_latest, status, error_message, uploaded_at, parsed_at, parse_error,
                    lifecycle_status, version_label, effective_from, effective_to,
                    document_family, supersedes_document_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    document.parsed_at.isoformat(timespec="seconds") if document.parsed_at else None,
                    document.parse_error,
                    document.lifecycle_status,
                    document.version_label,
                    _date_to_db(document.effective_from),
                    _date_to_db(document.effective_to),
                    document.document_family,
                    document.supersedes_document_id,
                    document.updated_at.isoformat(timespec="seconds") if document.updated_at else None,
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

    def list_by_family(self, document_family: str) -> list[Document]:
        with open_connection(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM documents
                WHERE document_family = ?
                ORDER BY uploaded_at DESC, id ASC
                """,
                (document_family,),
            ).fetchall()
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

    def update_lifecycle_status(self, document_id: str, lifecycle_status: str) -> None:
        if lifecycle_status not in self.VALID_LIFECYCLE_STATUSES:
            raise ValueError(f"Unsupported lifecycle status: {lifecycle_status}")
        with open_connection(self._database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE documents
                SET lifecycle_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (lifecycle_status, datetime.now().replace(microsecond=0).isoformat(timespec="seconds"), document_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Document not found: {document_id}")

    def update_version_metadata(
        self,
        document_id: str,
        *,
        version_label: str | None = None,
        effective_from: date | None = None,
        effective_to: date | None = None,
        document_family: str | None = None,
        supersedes_document_id: str | None = None,
    ) -> None:
        with open_connection(self._database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE documents
                SET version_label = ?, effective_from = ?, effective_to = ?,
                    document_family = ?, supersedes_document_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _clean_optional_text(version_label),
                    _date_to_db(effective_from),
                    _date_to_db(effective_to),
                    _clean_optional_text(document_family),
                    _clean_optional_text(supersedes_document_id),
                    datetime.now().replace(microsecond=0).isoformat(timespec="seconds"),
                    document_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Document not found: {document_id}")

    def promote_current(self, document_id: str) -> list[str]:
        now = datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            if row is None:
                raise ValueError(f"Document not found: {document_id}")
            family = row["document_family"] if "document_family" in row.keys() else None
            archived_ids: list[str] = []
            if family:
                archived_rows = connection.execute(
                    """
                    SELECT id FROM documents
                    WHERE document_family = ? AND id <> ? AND lifecycle_status = 'CURRENT'
                    ORDER BY uploaded_at DESC, id ASC
                    """,
                    (family, document_id),
                ).fetchall()
                archived_ids = [item["id"] for item in archived_rows]
                connection.execute(
                    """
                    UPDATE documents
                    SET lifecycle_status = 'ARCHIVED', updated_at = ?
                    WHERE document_family = ? AND id <> ? AND lifecycle_status = 'CURRENT'
                    """,
                    (now, family, document_id),
                )
            connection.execute(
                """
                UPDATE documents
                SET lifecycle_status = 'CURRENT', updated_at = ?
                WHERE id = ?
                """,
                (now, document_id),
            )
        return archived_ids

    def delete_document_records(self, document_id: str, display_name: str, *, deleted_fts_count: int, deleted_vector_count: int, internal_file_deleted: bool) -> DocumentDeleteResult:
        with open_connection(self._database_path) as connection:
            sheet_count = _count_table(connection, "document_sheets", document_id)
            cell_count = _count_table(connection, "document_cells", document_id)
            chunk_count = _count_table(connection, "document_chunks", document_id)
            index_count = _count_table(connection, "document_search_indexes", document_id)
            document_count = _count_table(connection, "documents", document_id)
            connection.execute("DELETE FROM document_search_indexes WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_cells WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_sheets WHERE document_id = ?", (document_id,))
            cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            if cursor.rowcount != 1:
                raise ValueError(f"Document not found: {document_id}")
        return DocumentDeleteResult(
            document_id=document_id,
            display_name=display_name,
            deleted_document_count=document_count,
            deleted_sheet_count=sheet_count,
            deleted_cell_count=cell_count,
            deleted_chunk_count=chunk_count,
            deleted_fts_count=deleted_fts_count,
            deleted_vector_count=deleted_vector_count,
            internal_file_deleted=internal_file_deleted,
            history_preserved=True,
            warning_code=None if index_count >= 0 else None,
        )


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _count_table(connection, table_name: str, document_id: str) -> int:
    if table_name == "documents":
        row = connection.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (document_id,)).fetchone()
    else:
        row = connection.execute(f"SELECT COUNT(*) FROM {table_name} WHERE document_id = ?", (document_id,)).fetchone()
    return int(row[0])


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
        lifecycle_status=row["lifecycle_status"] if "lifecycle_status" in row.keys() and row["lifecycle_status"] else "CURRENT",
        version_label=row["version_label"] if "version_label" in row.keys() else None,
        effective_from=_date_from_db(row["effective_from"]) if "effective_from" in row.keys() else None,
        effective_to=_date_from_db(row["effective_to"]) if "effective_to" in row.keys() else None,
        document_family=row["document_family"] if "document_family" in row.keys() else None,
        supersedes_document_id=row["supersedes_document_id"] if "supersedes_document_id" in row.keys() else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if "updated_at" in row.keys() and row["updated_at"] else None,
    )
