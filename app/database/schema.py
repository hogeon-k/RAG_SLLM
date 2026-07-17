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
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_original_name ON documents(original_name)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")

