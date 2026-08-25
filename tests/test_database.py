import sqlite3
from uuid import uuid4

import pytest

from wpt_manager.database.database import Database
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint


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


def test_list_collections(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first = Collection(
        name="Francie",
        description="První kolekce",
        source="Mapy.com",
        source_file="francie.gpx",
    )
    second = Collection(
        name="Itálie",
        description="Druhá kolekce",
        source="OsmAnd",
        source_file="italie.gpx",
    )
    database.save_collection(first)
    database.save_collection(second)

    collections = database.list_collections()

    assert collections == [first, second]


def test_update_collection(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Původní název")
    database.save_collection(collection)
    original_id = collection.id

    collection.name = "Nový název"
    collection.description = "Nový popis"
    collection.source = "OsmAnd"
    collection.source_file = "updated.gpx"
    database.update_collection(collection)
    loaded = database.get_collection(original_id)

    assert loaded is not None
    assert loaded.id == original_id
    assert loaded.name == "Nový název"
    assert loaded.description == "Nový popis"
    assert loaded.source == "OsmAnd"
    assert loaded.source_file == "updated.gpx"


def test_update_missing_collection_fails(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Neexistující")

    with pytest.raises(ValueError, match="Collection does not exist"):
        database.update_collection(collection)


def test_delete_collection(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Výlet do Francie")
    database.save_collection(collection)

    database.delete_collection(collection.id)

    assert database.get_collection(collection.id) is None


def test_delete_missing_collection_does_not_fail(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    database.delete_collection(uuid4())


def test_save_and_get_waypoint(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Výlet do Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="historic_archaeological_site",
        color="#FF8000",
        background="square",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )

    database.save_waypoint(waypoint, collection.id)
    loaded = database.get_waypoint(waypoint.id)

    assert loaded is not None
    assert loaded.id == waypoint.id
    assert loaded.name == waypoint.name
    assert loaded.latitude == waypoint.latitude
    assert loaded.longitude == waypoint.longitude
    assert loaded.icon == waypoint.icon
    assert loaded.color == waypoint.color
    assert loaded.background == waypoint.background
    assert loaded.note == waypoint.note
    assert loaded.comment == waypoint.comment


def test_get_missing_waypoint_returns_none(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    assert database.get_waypoint(uuid4()) is None


def test_save_waypoint_to_missing_collection_fails(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )

    with pytest.raises(sqlite3.IntegrityError):
        database.save_waypoint(waypoint, uuid4())


def test_save_waypoint_with_duplicate_id_fails(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Výlet do Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)

    with pytest.raises(sqlite3.IntegrityError):
        database.save_waypoint(waypoint, collection.id)


def test_list_waypoints_for_collection(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first_collection = Collection(name="Francie")
    second_collection = Collection(name="Itálie")
    database.save_collection(first_collection)
    database.save_collection(second_collection)
    first_waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="historic_archaeological_site",
        color="#FF8000",
        background="square",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )
    second_waypoint = Waypoint(
        name="Gorges du Toulourenc",
        latitude=44.216738,
        longitude=5.224684,
    )
    other_waypoint = Waypoint(
        name="Koloseum",
        latitude=41.890210,
        longitude=12.492231,
    )
    database.save_waypoint(first_waypoint, first_collection.id)
    database.save_waypoint(second_waypoint, first_collection.id)
    database.save_waypoint(other_waypoint, second_collection.id)

    waypoints = database.list_waypoints(first_collection.id)

    assert waypoints == [first_waypoint, second_waypoint]


def test_update_waypoint(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Původní název",
        latitude=1.0,
        longitude=2.0,
    )
    database.save_waypoint(waypoint, collection.id)
    original_id = waypoint.id

    waypoint.name = "Pont du Gard"
    waypoint.latitude = 43.947070
    waypoint.longitude = 4.535600
    waypoint.icon = "historic_archaeological_site"
    waypoint.color = "#FF8000"
    waypoint.background = "square"
    waypoint.note = "Zastavit na focení"
    waypoint.comment = "Velmi pěkné místo pro delší zastávku."
    database.update_waypoint(waypoint)
    loaded = database.get_waypoint(original_id)

    assert loaded == waypoint
    assert loaded is not None
    assert loaded.id == original_id


def test_update_missing_waypoint_fails(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    waypoint = Waypoint(
        name="Neexistující",
        latitude=1.0,
        longitude=2.0,
    )

    with pytest.raises(ValueError, match="Waypoint does not exist"):
        database.update_waypoint(waypoint)


def test_update_waypoints_is_atomic(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    existing = Waypoint(
        name="Original",
        latitude=1.0,
        longitude=2.0,
    )
    database.save_waypoint(existing, collection.id)
    existing.name = "Changed"
    missing = Waypoint(
        name="Missing",
        latitude=3.0,
        longitude=4.0,
    )

    with pytest.raises(ValueError, match="Waypoint does not exist"):
        database.update_waypoints([existing, missing])

    loaded = database.get_waypoint(existing.id)
    assert loaded is not None
    assert loaded.name == "Original"


def test_delete_waypoint(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)

    database.delete_waypoint(waypoint.id)

    assert database.get_waypoint(waypoint.id) is None


def test_delete_missing_waypoint_does_not_fail(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    database.delete_waypoint(uuid4())


def test_delete_collection_cascades_to_waypoints(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)

    database.delete_collection(collection.id)

    assert database.get_waypoint(waypoint.id) is None
