from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.schema import initialize_database


@dataclass(frozen=True)
class SearchIndexStatus:
    document_id: str
    status: str
    embedding_model: str | None
    model_fingerprint: str | None
    chunk_count: int
    fts_count: int
    vector_count: int
    indexed_at: datetime | None
    index_error: str | None
    content_fingerprint: str | None


class SearchIndexRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        initialize_database(database_path)

    def get(self, document_id: str) -> SearchIndexStatus | None:
        with open_connection(self._database_path) as connection:
            row = connection.execute(
                "SELECT * FROM document_search_indexes WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        return _row_to_status(row) if row else None

    def upsert_status(
        self,
        document_id: str,
        status: str,
        embedding_model: str | None = None,
        model_fingerprint: str | None = None,
        chunk_count: int = 0,
        fts_count: int = 0,
        vector_count: int = 0,
        indexed_at: datetime | None = None,
        index_error: str | None = None,
        content_fingerprint: str | None = None,
    ) -> None:
        with open_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO document_search_indexes (
                    document_id, status, embedding_model, model_fingerprint, chunk_count,
                    fts_count, vector_count, indexed_at, index_error, content_fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    status = excluded.status,
                    embedding_model = excluded.embedding_model,
                    model_fingerprint = excluded.model_fingerprint,
                    chunk_count = excluded.chunk_count,
                    fts_count = excluded.fts_count,
                    vector_count = excluded.vector_count,
                    indexed_at = excluded.indexed_at,
                    index_error = excluded.index_error,
                    content_fingerprint = excluded.content_fingerprint
                """,
                (
                    document_id,
                    status,
                    embedding_model,
                    model_fingerprint,
                    chunk_count,
                    fts_count,
                    vector_count,
                    indexed_at.isoformat(timespec="seconds") if indexed_at else None,
                    index_error,
                    content_fingerprint,
                ),
            )

    def ready_document_ids(self, document_ids: list[str] | None = None, include_archived: bool = False) -> list[str]:
        sql = """
            SELECT i.document_id
            FROM document_search_indexes i
            JOIN documents d ON d.id = i.document_id
            WHERE i.status = 'READY'
              AND d.status = 'COMPLETED'
        """
        params: list[object] = []
        if include_archived:
            sql += " AND d.lifecycle_status IN ('CURRENT', 'ARCHIVED')"
        else:
            sql += " AND d.lifecycle_status = 'CURRENT'"
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            sql += f" AND i.document_id IN ({placeholders})"
            params.extend(document_ids)
        sql += " ORDER BY CASE d.lifecycle_status WHEN 'CURRENT' THEN 0 ELSE 1 END, d.uploaded_at DESC, i.document_id ASC"
        with open_connection(self._database_path) as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [row["document_id"] for row in rows]

    def mark_stale(self, document_id: str) -> None:
        current = self.get(document_id)
        self.upsert_status(
            document_id,
            "STALE",
            embedding_model=current.embedding_model if current else None,
            model_fingerprint=current.model_fingerprint if current else None,
            chunk_count=current.chunk_count if current else 0,
            fts_count=current.fts_count if current else 0,
            vector_count=current.vector_count if current else 0,
            indexed_at=current.indexed_at if current else None,
            index_error=None,
            content_fingerprint=current.content_fingerprint if current else None,
        )


def _row_to_status(row) -> SearchIndexStatus:
    return SearchIndexStatus(
        document_id=row["document_id"],
        status=row["status"],
        embedding_model=row["embedding_model"],
        model_fingerprint=row["model_fingerprint"],
        chunk_count=row["chunk_count"],
        fts_count=row["fts_count"],
        vector_count=row["vector_count"],
        indexed_at=datetime.fromisoformat(row["indexed_at"]) if row["indexed_at"] else None,
        index_error=row["index_error"],
        content_fingerprint=row["content_fingerprint"],
    )
