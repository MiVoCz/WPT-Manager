import sqlite3
import pytest

from wpt_manager.database.database import Database
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track
from wpt_manager.io.gpx_track_importer import import_gpx_files_to_adventure


def test_adventure_crud_membership_order_and_cascades(tmp_path):
    database = Database(tmp_path / "adventures.db")
    database.initialize()
    first = Track("First", "first.gpx", distance_m=1000)
    second = Track("Second", "second.gpx", distance_m=2500)
    database.save_track(first)
    database.save_track(second)
    adventure = Adventure("Italy", description="2026")
    other = Adventure("Favorites")
    database.save_adventure(adventure)
    database.save_adventure(other)
    assert database.get_adventure(adventure.uuid) == adventure
    assert {item.uuid for item in database.list_adventures()} == {
        adventure.uuid, other.uuid
    }
    adventure.name = "Italy 2026"
    database.update_adventure(adventure)
    assert database.get_adventure(adventure.uuid).name == "Italy 2026"

    database.add_track_to_adventure(adventure.uuid, first.id)
    database.add_track_to_adventure(adventure.uuid, second.id)
    database.add_track_to_adventure(other.uuid, first.id)
    assert [item.id for item in database.list_adventure_tracks(adventure.uuid)] == [
        first.id, second.id
    ]
    assert sum(
        item.distance_m
        for item in database.list_adventure_tracks(adventure.uuid)
    ) == 3500
    database.set_adventure_track_order(
        adventure.uuid, [second.id, first.id]
    )
    assert [item.id for item in database.list_adventure_tracks(adventure.uuid)] == [
        second.id, first.id
    ]
    database.remove_track_from_adventure(adventure.uuid, first.id)
    assert [item.id for item in database.list_adventure_tracks(adventure.uuid)] == [
        second.id
    ]

    database.delete_adventure(adventure.uuid)
    assert database.get_track(second.id) is not None
    database.delete_track(first.id)
    assert database.list_adventure_tracks(other.uuid) == []
    assert database.get_adventure(other.uuid) is not None
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM adventure_tracks"
        ).fetchone()[0] == 0


def test_batch_membership_ignores_duplicates_and_is_atomic(tmp_path, monkeypatch):
    database = Database(tmp_path / "batch.db")
    database.initialize()
    adventure = Adventure("Batch")
    database.save_adventure(adventure)
    first = Track("First", "first.gpx")
    second = Track("Second", "second.gpx")
    database.save_track(first)
    database.save_track(second)
    database.add_tracks_to_adventure(
        adventure.uuid, [first.id, first.id, second.id]
    )
    assert [track.id for track in database.list_adventure_tracks(adventure.uuid)] == [
        first.id, second.id
    ]

    imported = [Track("Imported 1", "a.gpx"), Track("Imported 2", "b.gpx")]
    original = database._insert_track
    calls = 0

    def fail_second(connection, track):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.IntegrityError("failure")
        original(connection, track)

    monkeypatch.setattr(database, "_insert_track", fail_second)
    with pytest.raises(sqlite3.IntegrityError):
        database.save_tracks_to_adventure(imported, adventure.uuid)
    assert database.get_track(imported[0].id) is None
    assert [track.id for track in database.list_adventure_tracks(adventure.uuid)] == [
        first.id, second.id
    ]


def test_multi_file_import_preserves_file_and_track_order(tmp_path):
    database = Database(tmp_path / "imports.db")
    database.initialize()
    adventure = Adventure("Import")
    database.save_adventure(adventure)
    first_path = tmp_path / "first.gpx"
    second_path = tmp_path / "second.gpx"
    first_path.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'
        '<trk><name>A</name><trkseg/></trk>'
        '<trk><name>B</name><trkseg/></trk></gpx>', encoding="utf-8"
    )
    second_path.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'
        '<trk><name>C</name><trkseg/></trk></gpx>', encoding="utf-8"
    )
    tracks = import_gpx_files_to_adventure(
        database, [first_path, second_path], adventure.uuid
    )
    assert [track.name for track in tracks] == ["A", "B", "C"]
    assert [track.name for track in database.list_adventure_tracks(adventure.uuid)] == [
        "A", "B", "C"
    ]
