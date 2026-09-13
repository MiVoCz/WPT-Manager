import sqlite3
from contextlib import closing

import pytest

from wpt_manager.database.database import Database
from wpt_manager.models.collection import Collection
from wpt_manager.models.photo import Photo
from wpt_manager.models.track import Track
from wpt_manager.models.waypoint import Waypoint


def assert_v7(connection):
    columns = [
        ("uuid", "TEXT", 0, None, 1),
        ("track_uuid", "TEXT", 0, None, 0),
        ("name", "TEXT", 1, None, 0),
        ("taken_at", "TEXT", 0, None, 0),
        ("latitude", "REAL", 0, None, 0),
        ("longitude", "REAL", 0, None, 0),
        ("altitude", "REAL", 0, None, 0),
        ("source_type", "TEXT", 1, None, 0),
        ("source_url", "TEXT", 0, None, 0),
        ("thumbnail_url", "TEXT", 0, None, 0),
        ("external_id", "TEXT", 0, None, 0),
        ("description", "TEXT", 1, "''", 0),
        ("created_at", "TEXT", 1, None, 0),
    ]
    assert connection.execute("PRAGMA table_info(photos)").fetchall() == [
        (index, *column) for index, column in enumerate(columns)
    ]
    assert connection.execute("PRAGMA foreign_key_list(photos)").fetchall() == [
        (0, 0, "tracks", "track_uuid", "id", "NO ACTION", "SET NULL", "NONE")
    ]
    assert connection.execute(
        "SELECT sql FROM sqlite_master WHERE name='photos_source_external_id'"
    ).fetchone() == (
        "CREATE UNIQUE INDEX photos_source_external_id "
        "ON photos(source_type, external_id) WHERE external_id IS NOT NULL",
    )
    assert connection.execute("PRAGMA user_version").fetchone() == (7,)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def prepare_v6(path):
    database = Database(path)
    database.initialize()
    collection = Collection("Preserved")
    point = Waypoint("Place", 50, 14)
    track = Track("Track", "track.gpx")
    database.save_collection(collection)
    database.save_waypoint(point, collection.id)
    database.save_track(track)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TABLE photos")
        connection.execute("PRAGMA user_version = 6")
        connection.commit()
    return database


def dump(path):
    with closing(sqlite3.connect(path)) as connection:
        return list(connection.iterdump())


def test_fresh_and_existing_current_database_preserve_schema_and_photo(tmp_path):
    path = tmp_path / "current.db"
    database = Database(path)
    database.initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert_v7(connection)
    photo = Photo("Preserved", "local", latitude=50, longitude=14,
                  source_url="file:///photo.jpg", description="Original")
    database.save_photo(photo)
    before = dump(path)
    database.initialize()
    assert dump(path) == before
    assert database.get_photo(photo.id) == photo


def test_historical_migration_does_not_use_current_helper(tmp_path, monkeypatch):
    path = tmp_path / "historical.db"
    database = prepare_v6(path)
    before = dump(path)

    def changed_current_helper(connection):
        raise AssertionError("Historical migration called current schema helper")

    monkeypatch.setattr(Database, "_create_photo_table", staticmethod(changed_current_helper))
    database.initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert_v7(connection)
    assert set(before).issubset(set(dump(path)))


def test_failed_photo_migration_rolls_back_schema_index_version_and_data(tmp_path, monkeypatch):
    path = tmp_path / "rollback.db"
    database = prepare_v6(path)
    before = dump(path)
    historical = Database._create_photo_table_v7

    def fail_after_creation(connection):
        historical(connection)
        raise RuntimeError("Migration interrupted")

    monkeypatch.setattr(Database, "_create_photo_table_v7", staticmethod(fail_after_creation))
    with pytest.raises(RuntimeError, match="Migration interrupted"):
        database.initialize()
    assert dump(path) == before
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'photos%'"
        ).fetchall() == []
    monkeypatch.setattr(Database, "_create_photo_table_v7", staticmethod(historical))
    database.initialize()
    with closing(sqlite3.connect(path)) as connection:
        assert_v7(connection)
    assert set(before).issubset(set(dump(path)))
