from __future__ import annotations

from pathlib import Path

from app.database.connection import check_connection


class DatabaseRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    @property
    def database_path(self) -> Path:
        return self._database_path

    def health_check(self) -> bool:
        return check_connection(self._database_path)

