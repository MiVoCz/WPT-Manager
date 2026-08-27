from collections.abc import Iterable
from math import asin, cos, radians, sin, sqrt

from wpt_manager.models.duplicate_match import DuplicateMatch
from wpt_manager.models.waypoint import Waypoint


DEFAULT_DUPLICATE_THRESHOLD_M = 50.0
EARTH_RADIUS_M = 6_371_008.8


def find_nearest_duplicate(
    source: Waypoint,
    targets: Iterable[Waypoint],
    threshold_m: float = DEFAULT_DUPLICATE_THRESHOLD_M,
) -> DuplicateMatch | None:
    """Find the geographically nearest target within the threshold."""
    if threshold_m < 0:
        raise ValueError("Duplicate threshold cannot be negative.")

    nearest: DuplicateMatch | None = None
    for target in targets:
        distance_m = _geographic_distance_m(source, target)
        if distance_m <= threshold_m and (
            nearest is None or distance_m < nearest.distance_m
        ):
            nearest = DuplicateMatch(
                source=source,
                target=target,
                distance_m=distance_m,
            )

    return nearest


def _geographic_distance_m(first: Waypoint, second: Waypoint) -> float:
    return geographic_distance_m(
        first.latitude,
        first.longitude,
        second.latitude,
        second.longitude,
    )


def geographic_distance_m(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    """Return the great-circle distance between two coordinates in meters."""
    first_latitude_rad = radians(first_latitude)
    second_latitude_rad = radians(second_latitude)
    latitude_delta = second_latitude_rad - first_latitude_rad
    longitude_delta = radians(second_longitude - first_longitude)

    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude_rad)
        * cos(second_latitude_rad)
        * sin(longitude_delta / 2) ** 2
    )
    angular_distance = 2 * asin(sqrt(haversine))
    return EARTH_RADIUS_M * angular_distance
