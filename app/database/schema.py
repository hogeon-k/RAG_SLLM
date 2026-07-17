from __future__ import annotations

from pathlib import Path

from app.database.connection import open_connection


def initialize_database(database_path: Path) -> None:
    with open_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                file_hash TEXT NOT NULL UNIQUE,
                file_size_bytes INTEGER NOT NULL,
                version TEXT NULL,
                effective_date TEXT NULL,
                revised_date TEXT NULL,
                department TEXT NULL,
                is_latest INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL,
                error_message TEXT NULL,
                uploaded_at TEXT NOT NULL
            )
            """
        )
        _add_column_if_missing(connection, "documents", "parsed_at", "TEXT NULL")
        _add_column_if_missing(connection, "documents", "parse_error", "TEXT NULL")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_original_name ON documents(original_name)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_sheets (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                sheet_index INTEGER NOT NULL,
                sheet_state TEXT NOT NULL,
                max_row INTEGER NOT NULL,
                max_column INTEGER NOT NULL,
                non_empty_cell_count INTEGER NOT NULL,
                merged_range_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                UNIQUE(document_id, sheet_index)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_cells (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                sheet_id TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                coordinate TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                column_index INTEGER NOT NULL,
                value_type TEXT NOT NULL,
                text_value TEXT NOT NULL,
                formula TEXT NULL,
                cached_value TEXT NULL,
                merged_range TEXT NULL,
                is_merged_anchor INTEGER NOT NULL DEFAULT 0,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(sheet_id) REFERENCES document_sheets(id) ON DELETE CASCADE,
                UNIQUE(sheet_id, coordinate)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                sheet_id TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                cell_start TEXT NOT NULL,
                cell_end TEXT NOT NULL,
                cell_range TEXT NOT NULL,
                cell_refs_json TEXT NOT NULL,
                row_start INTEGER NOT NULL,
                row_end INTEGER NOT NULL,
                section TEXT NULL,
                article TEXT NULL,
                paragraph TEXT NULL,
                title TEXT NULL,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY(sheet_id) REFERENCES document_sheets(id) ON DELETE CASCADE,
                UNIQUE(document_id, sheet_id, chunk_index)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_sheets_document_id ON document_sheets(document_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_cells_document_id ON document_cells(document_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_cells_sheet_row ON document_cells(sheet_id, row_index)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_sheet_index ON document_chunks(sheet_id, chunk_index)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_content_hash ON document_chunks(content_hash)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS document_search_indexes (
                document_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                embedding_model TEXT NULL,
                model_fingerprint TEXT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                fts_count INTEGER NOT NULL DEFAULT 0,
                vector_count INTEGER NOT NULL DEFAULT 0,
                indexed_at TEXT NULL,
                index_error TEXT NULL,
                content_fingerprint TEXT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                original_name,
                sheet_name,
                section,
                article,
                title,
                content,
                tokenize='trigram'
            )
            """
        )


def _add_column_if_missing(connection, table_name: str, column_name: str, column_definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
