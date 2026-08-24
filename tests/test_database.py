import sqlite3

from wpt_manager.database.database import Database


def test_initialize_database(tmp_path):
    database_path = tmp_path / "wpt_manager.db"
    database = Database(database_path)

    database.initialize()

    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {row[0] for row in rows}
    assert "collections" in table_names
    assert "waypoints" in table_names

    database.initialize()


def test_foreign_keys_are_enabled(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")

    connection = database._connect()
    try:
        foreign_keys = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()
    finally:
        connection.close()

    assert foreign_keys == (1,)
