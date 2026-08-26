import sqlite3
from uuid import UUID, uuid4

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


def test_initialize_migrates_existing_waypoints_created_at(tmp_path):
    database_path = tmp_path / "wpt_manager.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE collections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            source_file TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE waypoints (
            id TEXT PRIMARY KEY,
            collection_id TEXT NOT NULL,
            name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            icon TEXT NOT NULL,
            color TEXT NOT NULL,
            background TEXT NOT NULL,
            note TEXT NOT NULL,
            comment TEXT NOT NULL,
            FOREIGN KEY (collection_id)
                REFERENCES collections(id) ON DELETE CASCADE
        );
        INSERT INTO collections
            (id, name, description, source, source_file)
        VALUES
            ('00000000-0000-0000-0000-000000000001',
             'Existing', '', '', '');
        INSERT INTO waypoints
            (id, collection_id, name, latitude, longitude,
             icon, color, background, note, comment)
        VALUES
            ('00000000-0000-0000-0000-000000000002',
             '00000000-0000-0000-0000-000000000001',
             'Existing waypoint', 1.0, 2.0,
             'marker', '#FF0000', 'circle', '', '');
        """
    )
    connection.close()

    database = Database(database_path)
    database.initialize()

    connection = sqlite3.connect(database_path)
    column = connection.execute(
        "SELECT name, type, \"notnull\", dflt_value "
        "FROM pragma_table_info('waypoints') WHERE name = 'created_at'"
    ).fetchone()
    row = connection.execute(
        "SELECT name, created_at FROM waypoints"
    ).fetchone()
    connection.close()

    assert column == ("created_at", "TEXT", 1, "CURRENT_TIMESTAMP")
    assert row is not None
    assert row[0] == "Existing waypoint"
    assert row[1]

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
    zulu = Collection(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        name="zulu",
    )
    uppercase_alpha = Collection(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        name="Alpha",
    )
    lowercase_alpha = Collection(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        name="alpha",
    )
    database.save_collection(zulu)
    database.save_collection(uppercase_alpha)
    database.save_collection(lowercase_alpha)

    collections = database.list_collections()

    assert collections == [lowercase_alpha, uppercase_alpha, zulu]


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

    assert waypoints == [second_waypoint, first_waypoint]


def test_list_waypoints_sorting(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Main")
    other_collection = Collection(name="Other")
    database.save_collection(collection)
    database.save_collection(other_collection)
    bravo = Waypoint(name="Bravo", latitude=1.0, longitude=1.0)
    alpha = Waypoint(name="alpha", latitude=2.0, longitude=2.0)
    charlie = Waypoint(name="charlie", latitude=3.0, longitude=3.0)
    other = Waypoint(name="Aaron", latitude=4.0, longitude=4.0)
    database.save_waypoint(bravo, collection.id)
    database.save_waypoint(alpha, collection.id)
    database.save_waypoint(charlie, collection.id)
    database.save_waypoint(other, other_collection.id)

    connection = sqlite3.connect(database.path)
    connection.execute(
        "UPDATE waypoints SET created_at = ? WHERE id = ?",
        ("2026-01-03 00:00:00", str(bravo.id)),
    )
    connection.execute(
        "UPDATE waypoints SET created_at = ? WHERE id = ?",
        ("2026-01-01 00:00:00", str(alpha.id)),
    )
    connection.execute(
        "UPDATE waypoints SET created_at = ? WHERE id = ?",
        ("2026-01-02 00:00:00", str(charlie.id)),
    )
    connection.commit()
    connection.close()

    assert database.list_waypoints(collection.id, "name") == [
        alpha,
        bravo,
        charlie,
    ]
    assert database.list_waypoints(collection.id, "created_at") == [
        alpha,
        charlie,
        bravo,
    ]


def test_list_waypoints_rejects_invalid_sort(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    with pytest.raises(ValueError, match="Unsupported waypoint sort"):
        database.list_waypoints(uuid4(), "invalid")


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


def test_delete_multiple_waypoints(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoints = [
        Waypoint(name="Alpha", latitude=1.0, longitude=1.0),
        Waypoint(name="Bravo", latitude=2.0, longitude=2.0),
    ]
    for waypoint in waypoints:
        database.save_waypoint(waypoint, collection.id)

    database.delete_waypoints([waypoint.id for waypoint in waypoints])

    assert all(
        database.get_waypoint(waypoint.id) is None
        for waypoint in waypoints
    )


def test_delete_waypoints_accepts_empty_list(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()

    database.delete_waypoints([])


def test_delete_waypoints_preserves_unselected_waypoints(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    selected = Waypoint(name="Selected", latitude=1.0, longitude=1.0)
    unselected = Waypoint(name="Unselected", latitude=2.0, longitude=2.0)
    database.save_waypoint(selected, collection.id)
    database.save_waypoint(unselected, collection.id)

    database.delete_waypoints([selected.id])

    assert database.get_waypoint(selected.id) is None
    assert database.get_waypoint(unselected.id) == unselected


def test_delete_waypoints_rolls_back_on_mid_operation_failure(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoints = [
        Waypoint(name="Alpha", latitude=1.0, longitude=1.0),
        Waypoint(name="Bravo", latitude=2.0, longitude=2.0),
    ]
    for waypoint in waypoints:
        database.save_waypoint(waypoint, collection.id)

    connection = sqlite3.connect(database.path)
    connection.execute(
        f"""
        CREATE TRIGGER fail_second_waypoint_delete
        BEFORE DELETE ON waypoints
        WHEN OLD.id = '{waypoints[1].id}'
        BEGIN
            SELECT RAISE(ABORT, 'Simulated delete failure');
        END
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="Simulated"):
        database.delete_waypoints([waypoint.id for waypoint in waypoints])

    assert all(
        database.get_waypoint(waypoint.id) == waypoint
        for waypoint in waypoints
    )


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
