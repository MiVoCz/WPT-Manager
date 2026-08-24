from pathlib import Path
import pytest

from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_reader import load_gpx
from wpt_manager.io.gpx_writer import save_gpx
from wpt_manager.models.waypoint import Waypoint


TEST_DATA = Path(__file__).parent / "data" / "mapy_export.gpx"


def test_load_mapy_gpx():
    waypoints = load_gpx(TEST_DATA)

    assert len(waypoints) == 3

    assert waypoints[0].name == "Pont du Gard"
    assert waypoints[0].latitude == 43.947070
    assert waypoints[0].longitude == 4.535600
    assert waypoints[0].note == ""
    assert waypoints[0].comment == ""
    assert waypoints[0].icon == "marker"
    assert waypoints[0].background == "circle"
    assert waypoints[0].color == "#FF0000"

    assert waypoints[1].name == "Gorges du Toulourenc"
    assert waypoints[1].latitude == 44.216738
    assert waypoints[1].longitude == 5.224684

    assert waypoints[2].name == "Grotte du Mas d’Azil"
    assert waypoints[2].latitude == 43.069735
    assert waypoints[2].longitude == 1.355004


def test_gpx_round_trip(tmp_path):
    original = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
        icon="historic_archaeological_site",
        background="square",
        color="#FF8000",
    )
    gpx_file = tmp_path / "round_trip.gpx"

    save_gpx([original], gpx_file)
    loaded_waypoints = load_gpx(gpx_file)

    assert len(loaded_waypoints) == 1
    loaded = loaded_waypoints[0]
    assert loaded.name == original.name
    assert loaded.latitude == original.latitude
    assert loaded.longitude == original.longitude
    assert loaded.note == original.note
    assert loaded.comment == original.comment
    assert loaded.icon == original.icon
    assert loaded.background == original.background
    assert loaded.color == original.color


def test_invalid_gpx(tmp_path):
    gpx_file = tmp_path / "invalid.gpx"
    gpx_file.write_text(
        "<gpx><invalid>",
        encoding="utf-8",
    )

    with pytest.raises(GpxReaderError):
        load_gpx(gpx_file)
