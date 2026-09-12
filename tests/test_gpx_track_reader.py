from datetime import datetime, timezone

import pytest

from wpt_manager.io.gpx_track_reader import load_gpx_tracks
from wpt_manager.io import gpx_track_reader
from wpt_manager.io.exceptions import GpxReaderError


def _write_gpx(tmp_path, body):
    path = tmp_path / "track.gpx"
    path.write_text(
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'
        + body + "</gpx>",
        encoding="utf-8",
    )
    return path


def test_load_simple_track_multiple_segments_and_metadata(tmp_path):
    path = _write_gpx(
        tmp_path,
        """<trk><name>Morning walk</name>
        <trkseg><trkpt lat="50" lon="14"><ele>250</ele>
        <time>2026-01-01T10:00:00Z</time></trkpt>
        <trkpt lat="50" lon="14.01"/></trkseg>
        <trkseg><trkpt lat="51" lon="15">
        <time>2026-01-01T10:10:00Z</time></trkpt></trkseg></trk>""",
    )
    track = load_gpx_tracks(path)[0]
    assert track.name == "Morning walk"
    assert track.point_count == 3
    assert [point.sequence for point in track.points] == [0, 1, 2]
    assert [point.segment_index for point in track.points] == [0, 0, 1]
    assert track.points[0].elevation == 250
    assert track.points[2].elevation is None
    assert track.start_time == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    assert track.end_time == datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc)
    assert track.distance_m == pytest.approx(714.7, rel=0.01)


def test_track_without_time_or_elevation(tmp_path):
    path = _write_gpx(
        tmp_path, '<trk><trkseg><trkpt lat="50" lon="14"/></trkseg></trk>'
    )
    track = load_gpx_tracks(path)[0]
    assert track.start_time is None
    assert track.end_time is None
    assert track.points[0].elevation is None


@pytest.mark.parametrize("latitude,longitude", [
    (0, 0), (-90, 0), (90, 0), (0, -180), (0, 180), (50.1234, 14.5678),
])
def test_valid_coordinate_boundaries(tmp_path, latitude, longitude):
    path = _write_gpx(tmp_path, f'<trk><trkseg><trkpt lat="{latitude}" lon="{longitude}"/></trkseg></trk>')
    point = load_gpx_tracks(path)[0].points[0]
    assert (point.latitude, point.longitude) == (latitude, longitude)


@pytest.mark.parametrize("axis,value", [
    ("lat", "90.0001"), ("lat", "-90.0001"),
    ("lon", "180.0001"), ("lon", "-180.0001"),
    *((axis, value) for axis in ("lat", "lon") for value in ("NaN", "Infinity", "-Infinity")),
])
def test_invalid_coordinates_rejected_before_point_or_distance(tmp_path, monkeypatch, axis, value):
    coordinates = {"lat": "0", "lon": "0", axis: value}
    path = _write_gpx(tmp_path, '<trk><trkseg><trkpt lat="{lat}" lon="{lon}"/></trkseg></trk>'.format(**coordinates))
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid coordinates reached point construction or distance calculation")
    monkeypatch.setattr(gpx_track_reader, "TrackPoint", unexpected)
    monkeypatch.setattr(gpx_track_reader, "_distance_m", unexpected)
    with pytest.raises(GpxReaderError, match="Latitude" if axis == "lat" else "Longitude"):
        load_gpx_tracks(path)


def test_multiple_tracks_keep_independent_sequences(tmp_path):
    path = _write_gpx(tmp_path, '<trk><name>A</name><trkseg><trkpt lat="0" lon="0"/></trkseg></trk>'
                      '<trk><name>B</name><trkseg><trkpt lat="90" lon="180"/></trkseg></trk>')
    tracks = load_gpx_tracks(path)
    assert [track.name for track in tracks] == ["A", "B"]
    assert [track.points[0].sequence for track in tracks] == [0, 0]
