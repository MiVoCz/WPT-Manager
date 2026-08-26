from dataclasses import dataclass
from enum import Enum, auto
from uuid import UUID

from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint

WaypointState = tuple[UUID, str, float, float, str, str, str, str, str]


class ConflictDecision(Enum):
    KEEP_TARGET = auto()
    USE_SOURCE = auto()
    KEEP_BOTH = auto()


@dataclass(frozen=True)
class MergeConflict:
    source: Waypoint
    target: Waypoint
    distance_m: float


@dataclass(frozen=True)
class WaypointMergePlan:
    new_waypoints: tuple[Waypoint, ...]
    conflicts: tuple[MergeConflict, ...]
    duplicate_threshold_m: float
    source_state: tuple[WaypointState, ...]
    target_state: tuple[WaypointState, ...]


@dataclass(frozen=True)
class MergePlan:
    source_collection: Collection
    target_collection: Collection
    new_waypoints: tuple[Waypoint, ...]
    conflicts: tuple[MergeConflict, ...]
    duplicate_threshold_m: float
    source_state: tuple[WaypointState, ...]
    target_state: tuple[WaypointState, ...]


@dataclass(frozen=True)
class MergeResult:
    added_count: int
    replaced_count: int
    skipped_count: int
    kept_both_count: int
