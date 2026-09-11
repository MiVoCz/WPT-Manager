from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from wpt_manager.models.photo import Photo
from wpt_manager.models.photo_track_match import PhotoTrackMatchStatus as Status
from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.photos.photo_track_matcher import PhotoTrackMatcher
from wpt_manager.validation.waypoint_duplicates import geographic_distance_m

BASE = datetime(2026, 9, 4, 15, 46, 15, tzinfo=timezone.utc)


def track(seconds=(0,), *, longitude=14.0, identifier=1):
    return Track("Track", "track.gpx", id=UUID(int=identifier), points=[
        TrackPoint(50.0, longitude, index, time=BASE + timedelta(seconds=second))
        for index, second in enumerate(seconds)
    ])


def photo(seconds=0, **changes):
    return Photo("Photo", "imagekit", taken_at=BASE + timedelta(seconds=seconds), **changes)


@pytest.mark.parametrize("seconds, expected, delta", [
    (0, Status.MATCHED, 0), (40, Status.MATCHED, 20),
    (60, Status.MATCHED, 0), (-300, Status.MATCHED, 300),
    (360, Status.MATCHED, 300), (-301, Status.NO_MATCH, None),
    (361, Status.NO_MATCH, None),
])
def test_time_range_and_nearest(seconds, expected, delta):
    result = PhotoTrackMatcher([track((60, 0))]).match_photo(photo(seconds))
    assert result.status == expected
    assert result.time_delta_seconds == delta


def test_gap_inside_track_is_rejected():
    assert PhotoTrackMatcher([track((0, 1000))]).match_photo(photo(500)).status == Status.NO_MATCH


@pytest.mark.parametrize("timestamp", [None, BASE.replace(tzinfo=None), "invalid"])
def test_unsafe_photo_time(timestamp):
    item = photo()
    item.taken_at = timestamp
    assert PhotoTrackMatcher([track()]).match_photo(item).status == Status.NO_TIMESTAMP


@pytest.mark.parametrize("timestamp", [None, BASE.replace(tzinfo=None), "bad"])
def test_unsafe_track_time(timestamp):
    candidate = track()
    candidate.points[0].time = timestamp
    candidate.start_time = BASE
    candidate.end_time = BASE
    assert PhotoTrackMatcher([candidate]).match_photo(photo()).status == Status.NO_MATCH


def test_empty_track():
    assert PhotoTrackMatcher([track(())]).match_photo(photo()).candidate_count == 0


@pytest.mark.parametrize("latitude, longitude, expected", [
    (None, None, Status.MATCHED), (50.0, 14.001, Status.MATCHED),
    (0.0, 0.0, Status.NO_MATCH), (50.0, None, Status.NO_MATCH),
    (float("nan"), 14.0, Status.NO_MATCH),
])
def test_optional_gps_validation(latitude, longitude, expected):
    result = PhotoTrackMatcher([track()]).match_photo(photo(latitude=latitude, longitude=longitude))
    assert result.status == expected


def test_best_time_wins_over_distance():
    best = track((0,), longitude=14.01)
    other = track((20,), longitude=14.0, identifier=2)
    result = PhotoTrackMatcher([other, best]).match_photo(photo(latitude=50, longitude=14))
    assert result.track_uuid == best.id and result.candidate_count == 2


def test_gps_breaks_equal_time_tie():
    best = track()
    other = track(longitude=14.01, identifier=2)
    result = PhotoTrackMatcher([other, best]).match_photo(photo(latitude=50, longitude=14))
    assert result.track_uuid == best.id and result.distance_meters == 0


@pytest.mark.parametrize("with_gps", [False, True])
def test_ambiguity_and_stable_order(with_gps):
    first, second = track(), track((10,), longitude=14.0001, identifier=2)
    item = photo(latitude=50, longitude=14) if with_gps else photo()
    result = PhotoTrackMatcher([first, second]).match_photo(item)
    assert result == PhotoTrackMatcher([second, first]).match_photo(item)
    assert result.status == Status.AMBIGUOUS and result.track_uuid is None
    assert result.candidate_count == 2


def test_exact_uuid_tie_is_deterministic_but_not_automatically_assigned():
    first, second = track(), track(identifier=2)
    result = PhotoTrackMatcher([second, first]).match_photo(photo())
    assert result == PhotoTrackMatcher([first, second]).match_photo(photo())
    assert result.status == Status.AMBIGUOUS


def test_third_candidate_cannot_hide_ambiguity():
    tracks = [track(), track((1,), longitude=14.01, identifier=2), track((2,), identifier=3)]
    assert PhotoTrackMatcher(tracks).match_photo(photo(latitude=50, longitude=14)).status == Status.AMBIGUOUS


def test_timezone_offsets_are_same_instant():
    candidate = track()
    candidate.points[0].time = datetime.fromisoformat("2026-09-04T17:46:15+02:00")
    item = photo()
    result = PhotoTrackMatcher([candidate]).match_photo(item)
    assert result.time_delta_seconds == 0 and result.status == Status.MATCHED
    item.taken_at = BASE.astimezone(timezone(timedelta(hours=-5)))
    assert PhotoTrackMatcher([candidate]).match_photo(item) == result


def test_haversine_known_distance():
    assert geographic_distance_m(0, 0, 0, 1) == pytest.approx(111195.08, abs=1)


def test_actual_points_override_stale_header():
    candidate = track()
    candidate.start_time = candidate.end_time = BASE - timedelta(days=3)
    assert PhotoTrackMatcher([candidate]).match_photo(photo()).status == Status.MATCHED


def test_nearest_time_not_nearest_position():
    candidate = track((0, 60))
    candidate.points[0].latitude = 0
    result = PhotoTrackMatcher([candidate]).match_photo(photo(1, latitude=50, longitude=14))
    assert result.status == Status.NO_MATCH
