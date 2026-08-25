import pytest

from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_duplicates import find_nearest_duplicate


METERS_PER_LATITUDE_DEGREE = 111_195.0


def waypoint_at_distance(name: str, distance_m: float) -> Waypoint:
    return Waypoint(
        name=name,
        latitude=50.0 + distance_m / METERS_PER_LATITUDE_DEGREE,
        longitude=14.0,
    )


def test_same_coordinates_are_duplicate_at_zero_metres():
    source = Waypoint(name="Source", latitude=50.0, longitude=14.0)
    target = Waypoint(name="Different name", latitude=50.0, longitude=14.0)

    match = find_nearest_duplicate(source, [target])

    assert match is not None
    assert match.source is source
    assert match.target is target
    assert match.distance_m == 0.0


def test_points_several_metres_apart_are_duplicate():
    source = waypoint_at_distance("Source", 0.0)
    target = waypoint_at_distance("Target", 7.0)

    match = find_nearest_duplicate(source, [target])

    assert match is not None
    assert match.distance_m == pytest.approx(7.0, abs=0.01)


def test_point_just_below_default_threshold_is_duplicate():
    source = waypoint_at_distance("Source", 0.0)
    target = waypoint_at_distance("Target", 49.9)

    match = find_nearest_duplicate(source, [target])

    assert match is not None
    assert match.distance_m < 50.0


def test_point_above_default_threshold_is_not_duplicate():
    source = waypoint_at_distance("Source", 0.0)
    target = waypoint_at_distance("Target", 50.1)

    assert find_nearest_duplicate(source, [target]) is None


def test_nearest_target_is_selected_when_multiple_are_in_range():
    source = waypoint_at_distance("Source", 0.0)
    farther = waypoint_at_distance("Farther", 30.0)
    nearest = waypoint_at_distance("Nearest", 5.0)
    middle = waypoint_at_distance("Middle", 15.0)

    match = find_nearest_duplicate(source, [farther, nearest, middle])

    assert match is not None
    assert match.target is nearest
    assert match.distance_m == pytest.approx(5.0, abs=0.01)


def test_custom_threshold_is_used():
    source = waypoint_at_distance("Source", 0.0)
    target = waypoint_at_distance("Target", 75.0)

    assert find_nearest_duplicate(source, [target]) is None
    match = find_nearest_duplicate(source, [target], threshold_m=80.0)

    assert match is not None
    assert match.target is target
