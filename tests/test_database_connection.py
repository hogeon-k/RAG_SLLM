from app.database.connection import check_connection, open_connection


def test_sqlite_connection_uses_tmp_path(tmp_path) -> None:
    database_path = tmp_path / "database" / "test.sqlite3"

    assert check_connection(database_path)
    assert database_path.exists()


def test_sqlite_foreign_keys_enabled(tmp_path) -> None:
    database_path = tmp_path / "database" / "test.sqlite3"

    with open_connection(database_path) as connection:
        row = connection.execute("PRAGMA foreign_keys").fetchone()

    assert row[0] == 1

