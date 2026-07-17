from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.database.connection import open_connection
from app.database.schema import initialize_database
from app.models.document import DocumentChunk, ParsedCell, ParsedSheet


class ExtractionRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        initialize_database(database_path)

    def replace_extraction(
        self,
        document_id: str,
        sheets: list[ParsedSheet] | tuple[ParsedSheet, ...],
        cells: list[ParsedCell] | tuple[ParsedCell, ...],
        chunks: list[DocumentChunk] | tuple[DocumentChunk, ...],
    ) -> None:
        parsed_at = datetime.now().replace(microsecond=0)
        with open_connection(self._database_path) as connection:
            connection.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_cells WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_sheets WHERE document_id = ?", (document_id,))
            connection.executemany(
                """
                INSERT INTO document_sheets (
                    id, document_id, sheet_name, sheet_index, sheet_state,
                    max_row, max_column, non_empty_cell_count, merged_range_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        sheet.id,
                        sheet.document_id,
                        sheet.sheet_name,
                        sheet.sheet_index,
                        sheet.sheet_state,
                        sheet.max_row,
                        sheet.max_column,
                        sheet.non_empty_cell_count,
                        sheet.merged_range_count,
                        sheet.created_at.isoformat(timespec="seconds"),
                    )
                    for sheet in sheets
                ],
            )
            connection.executemany(
                """
                INSERT INTO document_cells (
                    id, document_id, sheet_id, sheet_name, coordinate,
                    row_index, column_index, value_type, text_value, formula, cached_value,
                    merged_range, is_merged_anchor, is_hidden
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        cell.id,
                        cell.document_id,
                        cell.sheet_id,
                        cell.sheet_name,
                        cell.coordinate,
                        cell.row_index,
                        cell.column_index,
                        cell.value_type,
                        cell.text_value,
                        cell.formula,
                        cell.cached_value,
                        cell.merged_range,
                        1 if cell.is_merged_anchor else 0,
                        1 if cell.is_hidden else 0,
                    )
                    for cell in cells
                ],
            )
            connection.executemany(
                """
                INSERT INTO document_chunks (
                    id, document_id, sheet_id, sheet_name, cell_start, cell_end, cell_range,
                    cell_refs_json, row_start, row_end, section, article, paragraph, title,
                    content, chunk_index, content_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.sheet_id,
                        chunk.sheet_name,
                        chunk.cell_start,
                        chunk.cell_end,
                        chunk.cell_range,
                        json.dumps(list(chunk.cell_refs), ensure_ascii=False),
                        chunk.row_start,
                        chunk.row_end,
                        chunk.section,
                        chunk.article,
                        chunk.paragraph,
                        chunk.title,
                        chunk.content,
                        chunk.chunk_index,
                        chunk.content_hash,
                        chunk.created_at.isoformat(timespec="seconds"),
                    )
                    for chunk in chunks
                ],
            )
            connection.execute(
                "UPDATE documents SET status = ?, parsed_at = ?, parse_error = NULL WHERE id = ?",
                ("PARSED", parsed_at.isoformat(timespec="seconds"), document_id),
            )
            connection.execute(
                """
                UPDATE document_search_indexes
                SET status = 'STALE', index_error = NULL
                WHERE document_id = ?
                """,
                (document_id,),
            )

    def list_sheets(self, document_id: str) -> list[ParsedSheet]:
        with open_connection(self._database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM document_sheets WHERE document_id = ? ORDER BY sheet_index",
                (document_id,),
            ).fetchall()
        return [_row_to_sheet(row) for row in rows]

    def list_cells(self, document_id: str, sheet_id: str | None = None, sheet_name: str | None = None) -> list[ParsedCell]:
        sql = "SELECT * FROM document_cells WHERE document_id = ?"
        params: list[object] = [document_id]
        if sheet_id:
            sql += " AND sheet_id = ?"
            params.append(sheet_id)
        if sheet_name:
            sql += " AND sheet_name = ?"
            params.append(sheet_name)
        sql += " ORDER BY sheet_name, row_index, column_index"
        with open_connection(self._database_path) as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [_row_to_cell(row) for row in rows]

    def list_chunks(self, document_id: str) -> list[DocumentChunk]:
        with open_connection(self._database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY sheet_name, chunk_index",
                (document_id,),
            ).fetchall()
        return [_row_to_chunk(row) for row in rows]

    def get_chunk(self, chunk_id: str) -> DocumentChunk | None:
        with open_connection(self._database_path) as connection:
            row = connection.execute("SELECT * FROM document_chunks WHERE id = ?", (chunk_id,)).fetchone()
        return _row_to_chunk(row) if row else None

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[DocumentChunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with open_connection(self._database_path) as connection:
            rows = connection.execute(
                f"SELECT * FROM document_chunks WHERE id IN ({placeholders})",
                tuple(chunk_ids),
            ).fetchall()
        chunks = {}
        for row in rows:
            chunk = _row_to_chunk(row)
            chunks[chunk.id] = chunk
        return [chunks[chunk_id] for chunk_id in chunk_ids if chunk_id in chunks]

    def count_chunks(self, document_id: str) -> int:
        return self._count("document_chunks", document_id)

    def count_cells(self, document_id: str) -> int:
        return self._count("document_cells", document_id)

    def counts_by_document(self, document_id: str) -> tuple[int, int, int]:
        with open_connection(self._database_path) as connection:
            sheet_count = connection.execute(
                "SELECT COUNT(*) FROM document_sheets WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            cell_count = connection.execute(
                "SELECT COUNT(*) FROM document_cells WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            chunk_count = connection.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
        return int(sheet_count), int(cell_count), int(chunk_count)

    def _count(self, table_name: str, document_id: str) -> int:
        with open_connection(self._database_path) as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table_name} WHERE document_id = ?", (document_id,)).fetchone()
        return int(row[0])


def _row_to_sheet(row) -> ParsedSheet:
    return ParsedSheet(
        id=row["id"],
        document_id=row["document_id"],
        sheet_name=row["sheet_name"],
        sheet_index=row["sheet_index"],
        sheet_state=row["sheet_state"],
        max_row=row["max_row"],
        max_column=row["max_column"],
        non_empty_cell_count=row["non_empty_cell_count"],
        merged_range_count=row["merged_range_count"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_cell(row) -> ParsedCell:
    return ParsedCell(
        id=row["id"],
        document_id=row["document_id"],
        sheet_id=row["sheet_id"],
        sheet_name=row["sheet_name"],
        coordinate=row["coordinate"],
        row_index=row["row_index"],
        column_index=row["column_index"],
        value_type=row["value_type"],
        text_value=row["text_value"],
        formula=row["formula"],
        cached_value=row["cached_value"],
        merged_range=row["merged_range"],
        is_merged_anchor=bool(row["is_merged_anchor"]),
        is_hidden=bool(row["is_hidden"]),
    )


def _row_to_chunk(row) -> DocumentChunk:
    return DocumentChunk(
        id=row["id"],
        document_id=row["document_id"],
        sheet_id=row["sheet_id"],
        sheet_name=row["sheet_name"],
        cell_start=row["cell_start"],
        cell_end=row["cell_end"],
        cell_range=row["cell_range"],
        cell_refs=tuple(json.loads(row["cell_refs_json"])),
        row_start=row["row_start"],
        row_end=row["row_end"],
        section=row["section"],
        article=row["article"],
        paragraph=row["paragraph"],
        title=row["title"],
        content=row["content"],
        chunk_index=row["chunk_index"],
        content_hash=row["content_hash"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
