from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.schema import initialize_database
from app.models.document import HistoryFilters, HistoryListResult, HistorySource, QuestionHistory


class HistoryRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        initialize_database(database_path)

    def save(self, history: QuestionHistory) -> None:
        with open_connection(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO question_histories (
                    history_id, request_id, question, answer, status, insufficient_evidence,
                    error_code, error_message, search_mode, requested_top_k, retrieved_count,
                    used_evidence_count, ollama_model, total_duration_ms, retrieval_duration_ms,
                    generation_duration_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    history.history_id,
                    history.request_id,
                    history.question,
                    history.answer,
                    history.status,
                    1 if history.insufficient_evidence else 0,
                    history.error_code,
                    history.error_message,
                    history.search_mode,
                    history.requested_top_k,
                    history.retrieved_count,
                    history.used_evidence_count,
                    history.ollama_model,
                    history.total_duration_ms,
                    history.retrieval_duration_ms,
                    history.generation_duration_ms,
                    history.created_at.isoformat(timespec="seconds"),
                ),
            )
            connection.executemany(
                """
                INSERT INTO question_history_sources (
                    history_source_id, history_id, evidence_id, chunk_id, document_id, sheet_id,
                    source_rank, document_display_name, sheet_name, article, title, cell_range,
                    cell_refs_json, content, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        source.history_source_id,
                        source.history_id,
                        source.evidence_id,
                        source.chunk_id,
                        source.document_id,
                        source.sheet_id,
                        source.source_rank,
                        source.document_display_name,
                        source.sheet_name,
                        source.article,
                        source.title,
                        source.cell_range,
                        json.dumps(list(source.cell_refs), ensure_ascii=False),
                        source.content,
                        source.created_at.isoformat(timespec="seconds"),
                    )
                    for source in history.sources
                ],
            )

    def list(self, filters: HistoryFilters) -> HistoryListResult:
        where_sql, params = _build_where(filters)
        count_sql = f"SELECT COUNT(DISTINCT h.history_id) FROM question_histories h {where_sql}"
        list_sql = f"""
            SELECT h.*
            FROM question_histories h
            {where_sql}
            GROUP BY h.history_id
            ORDER BY h.created_at DESC, h.history_id DESC
            LIMIT ? OFFSET ?
        """
        with open_connection(self._database_path) as connection:
            total = int(connection.execute(count_sql, tuple(params)).fetchone()[0])
            rows = connection.execute(list_sql, tuple(params + [filters.limit, filters.offset])).fetchall()
        return HistoryListResult([_row_to_history(row, ()) for row in rows], total, filters.limit, filters.offset)

    def get(self, history_id: str) -> QuestionHistory | None:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT * FROM question_histories WHERE history_id = ?", (history_id,)).fetchone()
            if row is None:
                return None
            source_rows = connection.execute(
                """
                SELECT *
                FROM question_history_sources
                WHERE history_id = ?
                ORDER BY source_rank ASC, history_source_id ASC
                """,
                (history_id,),
            ).fetchall()
        return _row_to_history(row, tuple(_row_to_source(source) for source in source_rows))

    def delete(self, history_id: str) -> bool:
        with open_connection(self._database_path) as connection:
            cursor = connection.execute("DELETE FROM question_histories WHERE history_id = ?", (history_id,))
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        with open_connection(self._database_path) as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM question_histories").fetchone()[0])
            connection.execute("DELETE FROM question_histories")
        return count

    def count(self) -> int:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM question_histories").fetchone()
        return int(row[0])


def _build_where(filters: HistoryFilters) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.status:
        clauses.append("h.status = ?")
        params.append(filters.status)
    if filters.start_date:
        clauses.append("h.created_at >= ?")
        params.append(filters.start_date.isoformat())
    if filters.end_date:
        clauses.append("h.created_at < ?")
        params.append(filters.end_date.isoformat() + "T23:59:59")
    if filters.search_text:
        pattern = f"%{_escape_like(filters.search_text)}%"
        clauses.append(
            """
            (
                h.question LIKE ? ESCAPE '\\'
                OR h.answer LIKE ? ESCAPE '\\'
                OR EXISTS (
                    SELECT 1 FROM question_history_sources s
                    WHERE s.history_id = h.history_id
                    AND (
                        s.document_display_name LIKE ? ESCAPE '\\'
                        OR s.sheet_name LIKE ? ESCAPE '\\'
                        OR s.article LIKE ? ESCAPE '\\'
                        OR s.title LIKE ? ESCAPE '\\'
                    )
                )
            )
            """
        )
        params.extend((pattern, pattern, pattern, pattern, pattern, pattern))
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where_sql, params


def _row_to_history(row, sources: tuple[HistorySource, ...]) -> QuestionHistory:
    return QuestionHistory(
        history_id=row["history_id"],
        request_id=row["request_id"],
        question=row["question"],
        answer=row["answer"],
        status=row["status"],
        insufficient_evidence=bool(row["insufficient_evidence"]),
        error_code=row["error_code"],
        error_message=row["error_message"],
        search_mode=row["search_mode"],
        requested_top_k=row["requested_top_k"],
        retrieved_count=row["retrieved_count"],
        used_evidence_count=row["used_evidence_count"],
        ollama_model=row["ollama_model"],
        total_duration_ms=row["total_duration_ms"],
        retrieval_duration_ms=row["retrieval_duration_ms"],
        generation_duration_ms=row["generation_duration_ms"],
        created_at=datetime.fromisoformat(row["created_at"]),
        sources=sources,
    )


def _row_to_source(row) -> HistorySource:
    return HistorySource(
        history_source_id=row["history_source_id"],
        history_id=row["history_id"],
        evidence_id=row["evidence_id"],
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        sheet_id=row["sheet_id"],
        source_rank=row["source_rank"],
        document_display_name=row["document_display_name"],
        sheet_name=row["sheet_name"],
        article=row["article"],
        title=row["title"],
        cell_range=row["cell_range"],
        cell_refs=tuple(json.loads(row["cell_refs_json"])),
        content=row["content"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
