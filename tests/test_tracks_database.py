import sqlite3
from datetime import datetime, timezone

import pytest

from wpt_manager.database.database import Database, SCHEMA_VERSION
from wpt_manager.models.track import DEFAULT_TRACK_COLOR, Track, TrackPoint


def test_track_crud_and_cascade(tmp_path):
    database = Database(tmp_path / "tracks.db")
    database.initialize()
    point_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    track = Track(
        "Trip", "trip.gpx",
        [TrackPoint(50, 14, 0, 200, point_time)],
        start_time=point_time, end_time=point_time,
        distance_m=0, point_count=1,
    )
    database.save_track(track)
    assert database.get_track(track.id).name == "Trip"
    assert database.get_track(track.id).color == DEFAULT_TRACK_COLOR
    assert database.list_tracks()[0].id == track.id
    assert database.list_track_points(track.id) == track.points
    database.delete_track(track.id)
    assert database.get_track(track.id) is None
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM track_points").fetchone()[0] == 0


def test_saving_multiple_tracks_is_atomic(tmp_path):
    database = Database(tmp_path / "tracks.db")
    database.initialize()
    first = Track("First", "x.gpx")
    duplicate = Track("Duplicate", "x.gpx", id=first.id)
    with pytest.raises(sqlite3.IntegrityError):
        database.save_tracks([first, duplicate])
    assert database.list_tracks() == []


def test_track_color_is_persisted(tmp_path):
    database = Database(tmp_path / "tracks.db")
    database.initialize()
    track = Track("Colored", "track.gpx", color="#AABBCC")
    database.save_track(track)
    assert database.get_track(track.id).color == "#AABBCC"
    track.color = "#112233"
    database.update_track(track)
    assert database.get_track(track.id).color == "#112233"


def test_migrate_schema_3_tracks_adds_default_color(tmp_path):
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT NOT NULL,
            description TEXT NOT NULL, source TEXT NOT NULL,
            source_file TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE waypoints (id TEXT PRIMARY KEY, collection_id TEXT NOT NULL,
            name TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
            icon TEXT NOT NULL, color TEXT NOT NULL, background TEXT NOT NULL,
            note TEXT NOT NULL, comment TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE);
        CREATE TABLE tracks (id TEXT PRIMARY KEY, name TEXT NOT NULL,
            source_file TEXT NOT NULL, created_at TEXT NOT NULL,
            start_time TEXT, end_time TEXT, distance_m REAL NOT NULL,
            point_count INTEGER NOT NULL);
        CREATE TABLE track_points (track_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            latitude REAL NOT NULL, longitude REAL NOT NULL, elevation REAL, time TEXT,
            PRIMARY KEY (track_id, sequence),
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE);
        INSERT INTO tracks VALUES ('00000000-0000-0000-0000-000000000001',
            'Old', 'old.gpx', '2026-01-01T00:00:00+00:00', NULL, NULL, 0, 0);
        INSERT INTO track_points VALUES (
            '00000000-0000-0000-0000-000000000001', 0, 50, 14, NULL, NULL);
        PRAGMA user_version = 3;
        """
    )
    connection.close()
    database = Database(path)
    database.initialize()
    assert database.list_tracks()[0].color == DEFAULT_TRACK_COLOR
    assert database.list_track_points(database.list_tracks()[0].id)[0].segment_index == 0
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
