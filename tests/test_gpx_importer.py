import sqlite3
from pathlib import Path

import pytest

from wpt_manager.database.database import Database
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_importer import import_gpx
from wpt_manager.models.waypoint import Waypoint


TEST_DATA = Path(__file__).parent / "data" / "mapy_export.gpx"


def test_import_gpx(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    collection = import_gpx(
        database,
        TEST_DATA,
        "Výlet do Francie",
        "Místa vybraná pro cestu.",
    )

    loaded_collection = database.get_collection(collection.id)
    assert loaded_collection == collection
    assert collection.source == "mapy.com"
    assert collection.source_file == "mapy_export.gpx"

    waypoints = database.list_waypoints(collection.id)
    assert len(waypoints) == 3
    assert [
        (waypoint.name, waypoint.latitude, waypoint.longitude)
        for waypoint in waypoints
    ] == [
        ("Gorges du Toulourenc", 44.216738, 5.224684),
        ("Grotte du Mas d’Azil", 43.069735, 1.355004),
        ("Pont du Gard", 43.947070, 4.535600),
    ]


def test_import_gpx_rolls_back_on_storage_error(tmp_path, monkeypatch):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    waypoint = Waypoint(
        name="Duplicitní waypoint",
        latitude=1.0,
        longitude=2.0,
    )
    monkeypatch.setattr(
        "wpt_manager.io.gpx_importer.load_gpx",
        lambda path: [waypoint, waypoint],
    )

    with pytest.raises(sqlite3.IntegrityError):
        import_gpx(database, TEST_DATA, "Neúspěšný import")

    assert database.list_collections() == []

    connection = database._connect()
    try:
        waypoint_count = connection.execute(
            "SELECT COUNT(*) FROM waypoints"
        ).fetchone()
    finally:
        connection.close()

    assert waypoint_count == (0,)


def test_invalid_waypoint_rolls_back_entire_gpx_import(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    gpx_file = tmp_path / "partially_invalid.gpx"
    gpx_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'
        '<wpt lat="50" lon="14"><name>Valid first</name></wpt>'
        '<wpt lat="95" lon="15"><name>Invalid second</name></wpt>'
        "</gpx>",
        encoding="utf-8",
    )

    with pytest.raises(GpxReaderError, match="Invalid second"):
        import_gpx(database, gpx_file, "Must not be created")

    assert database.list_collections() == []
    connection = database._connect()
    try:
        waypoint_count = connection.execute(
            "SELECT COUNT(*) FROM waypoints"
        ).fetchone()
    finally:
        connection.close()
    assert waypoint_count == (0,)
