from uuid import uuid4

import pytest

from wpt_manager.database.database import Database
from wpt_manager.io.gpx_exporter import export_collection_gpx
from wpt_manager.io.gpx_reader import load_gpx
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint


def test_export_collection_gpx(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    other_collection = Collection(name="Itálie")
    database.save_collection(collection)
    database.save_collection(other_collection)
    first_waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
        icon="historic_archaeological_site",
        background="square",
        color="#FF8000",
    )
    second_waypoint = Waypoint(
        name="Gorges du Toulourenc",
        latitude=44.216738,
        longitude=5.224684,
        note="Krátká poznámka",
        comment="Podrobný komentář",
        icon="natural_water",
        background="circle",
        color="#0080FF",
    )
    other_waypoint = Waypoint(
        name="Koloseum",
        latitude=41.890210,
        longitude=12.492231,
    )
    database.save_waypoint(first_waypoint, collection.id)
    database.save_waypoint(second_waypoint, collection.id)
    database.save_waypoint(other_waypoint, other_collection.id)
    output_file = tmp_path / "francie.gpx"

    export_collection_gpx(database, collection.id, output_file)

    assert output_file.exists()
    exported_waypoints = load_gpx(output_file)
    assert [
        (
            waypoint.name,
            waypoint.latitude,
            waypoint.longitude,
            waypoint.note,
            waypoint.comment,
            waypoint.icon,
            waypoint.background,
            waypoint.color,
        )
        for waypoint in exported_waypoints
    ] == [
        (
            waypoint.name,
            waypoint.latitude,
            waypoint.longitude,
            waypoint.note,
            waypoint.comment,
            waypoint.icon,
            waypoint.background,
            waypoint.color,
        )
        for waypoint in [second_waypoint, first_waypoint]
    ]


def test_export_missing_collection_fails(tmp_path):
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection_id = uuid4()

    with pytest.raises(ValueError, match="Collection does not exist"):
        export_collection_gpx(
            database,
            collection_id,
            tmp_path / "missing.gpx",
        )
