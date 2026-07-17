from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def open_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_connection(database_path: Path) -> bool:
    with open_connection(database_path) as connection:
        row = connection.execute("SELECT 1 AS ok").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
    return bool(row and row["ok"] == 1 and foreign_keys and foreign_keys[0] == 1)

