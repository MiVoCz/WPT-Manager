import sqlite3
from uuid import uuid4

import pytest

from wpt_manager.database.database import Database
from wpt_manager.models.collection import Collection


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


def test_save_and_get_collection(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(
        name="Výlet do Francie",
        description="Zajímavá místa ve Francii.",
        source="Mapy.com",
        source_file="francie.gpx",
    )

    database.save_collection(collection)
    loaded = database.get_collection(collection.id)

    assert loaded is not None
    assert loaded.id == collection.id
    assert loaded.name == collection.name
    assert loaded.description == collection.description
    assert loaded.source == collection.source
    assert loaded.source_file == collection.source_file


def test_get_missing_collection_returns_none(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    assert database.get_collection(uuid4()) is None


def test_save_collection_with_duplicate_id_fails(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Výlet do Francie")
    database.save_collection(collection)

    with pytest.raises(sqlite3.IntegrityError):
        database.save_collection(collection)
