from dataclasses import dataclass

from wpt_manager.models.waypoint import Waypoint


@dataclass(frozen=True)
class DuplicateMatch:
    source: Waypoint
    target: Waypoint
    distance_m: float
