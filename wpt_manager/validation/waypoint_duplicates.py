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
    first_latitude = radians(first.latitude)
    second_latitude = radians(second.latitude)
    latitude_delta = second_latitude - first_latitude
    longitude_delta = radians(second.longitude - first.longitude)

    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(first_latitude)
        * cos(second_latitude)
        * sin(longitude_delta / 2) ** 2
    )
    angular_distance = 2 * asin(sqrt(haversine))
    return EARTH_RADIUS_M * angular_distance
