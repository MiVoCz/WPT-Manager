from pathlib import Path
import pytest

from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_reader import load_gpx


TEST_DATA = Path(__file__).parent / "data" / "mapy_export.gpx"


def test_load_mapy_gpx():
    waypoints = load_gpx(TEST_DATA)

    assert len(waypoints) == 3

    assert waypoints[0].name == "Pont du Gard"
    assert waypoints[0].latitude == 43.947070
    assert waypoints[0].longitude == 4.535600

    assert waypoints[1].name == "Gorges du Toulourenc"
    assert waypoints[1].latitude == 44.216738
    assert waypoints[1].longitude == 5.224684

    assert waypoints[2].name == "Grotte du Mas d’Azil"
    assert waypoints[2].latitude == 43.069735
    assert waypoints[2].longitude == 1.355004

def test_invalid_gpx(tmp_path):
    gpx_file = tmp_path / "invalid.gpx"
    gpx_file.write_text(
        "<gpx><invalid>",
        encoding="utf-8",
    )

    with pytest.raises(GpxReaderError):
        load_gpx(gpx_file)