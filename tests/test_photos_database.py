import sqlite3
from datetime import datetime, timezone

from wpt_manager.database.database import Database, SCHEMA_VERSION
from wpt_manager.models.photo import Photo
from wpt_manager.models.track import Track


def test_photo_crud_lists_and_nullable_track(tmp_path):
    database = Database(tmp_path / "photos.db")
    database.initialize()
    track = Track("Track", "track.gpx")
    database.save_track(track)
    photo = Photo(
        "Lake", "local", track_uuid=track.id,
        taken_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        latitude=46.1, longitude=11.2, altitude=320.0,
        source_url="file:///lake.jpg", description="Before",
    )
    standalone = Photo("Solo", "local")
    database.save_photo(photo)
    database.save_photo(standalone)

    loaded = database.get_photo(photo.id)
    assert loaded == photo
    assert database.list_photos_for_track(track.id) == [photo]
    assert database.list_standalone_photos() == [standalone]
    assert {item.id for item in database.list_photos()} == {
        photo.id, standalone.id
    }
    photo.name = "Mountain lake"
    photo.description = "After"
    database.update_photo(photo)
    assert database.get_photo(photo.id).description == "After"
    database.delete_photo(standalone.id)
    assert database.get_photo(standalone.id) is None


def test_delete_track_sets_photo_track_to_null_without_deleting_photo(tmp_path):
    database = Database(tmp_path / "set-null.db")
    database.initialize()
    track = Track("Track", "track.gpx")
    database.save_track(track)
    photo = Photo("Photo", "local", track_uuid=track.id)
    database.save_photo(photo)
    database.delete_track(track.id)
    assert database.get_photo(photo.id).track_uuid is None
    assert database.list_standalone_photos()[0].id == photo.id


def test_schema_6_migrates_to_photo_schema(tmp_path):
    path = tmp_path / "migration.db"
    database = Database(path)
    database.initialize()
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE photos")
    connection.execute("PRAGMA user_version = 6")
    connection.commit()
    connection.close()
    database.initialize()
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        foreign_keys = connection.execute("PRAGMA foreign_key_list(photos)").fetchall()
        assert any(row[2] == "tracks" and row[6] == "SET NULL" for row in foreign_keys)
    finally:
        connection.close()


def test_photo_has_no_direct_adventure_storage(tmp_path):
    path = tmp_path / "derived.db"
    database = Database(path)
    database.initialize()
    connection = sqlite3.connect(path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(photos)")}
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    finally:
        connection.close()
    assert "adventure_uuid" not in columns
    assert "photo_adventures" not in tables
