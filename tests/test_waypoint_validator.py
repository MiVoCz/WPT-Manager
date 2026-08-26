import pytest

from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_validator import validate_waypoint


def test_valid_waypoint():
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )

    assert validate_waypoint(waypoint) == []


def test_empty_name():
    waypoint = Waypoint(
        name="",
        latitude=43.947070,
        longitude=4.535600,
    )

    assert validate_waypoint(waypoint) == [
        "Waypoint name cannot be empty."
    ]


def test_invalid_latitude():
    waypoint = Waypoint(
        name="Invalid",
        latitude=95,
        longitude=4.535600,
    )

    assert validate_waypoint(waypoint) == [
        "Latitude must be between -90 and 90."
    ]


def test_invalid_longitude():
    waypoint = Waypoint(
        name="Invalid",
        latitude=43.947070,
        longitude=200,
    )

    assert validate_waypoint(waypoint) == [
        "Longitude must be between -180 and 180."
    ]


@pytest.mark.parametrize(
    "latitude",
    [float("nan"), float("inf"), -float("inf")],
)
def test_non_finite_latitude(latitude):
    waypoint = Waypoint(
        name="Invalid",
        latitude=latitude,
        longitude=4.535600,
    )

    assert validate_waypoint(waypoint) == [
        "Latitude must be a finite number."
    ]


@pytest.mark.parametrize(
    "longitude",
    [float("nan"), float("inf"), -float("inf")],
)
def test_non_finite_longitude(longitude):
    waypoint = Waypoint(
        name="Invalid",
        latitude=43.947070,
        longitude=longitude,
    )

    assert validate_waypoint(waypoint) == [
        "Longitude must be a finite number."
    ]
