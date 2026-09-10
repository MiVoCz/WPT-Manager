from datetime import datetime, timezone

import pytest

from wpt_manager.io.gpx_track_reader import load_gpx_tracks


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
