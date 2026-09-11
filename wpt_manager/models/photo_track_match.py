from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class PhotoTrackMatchStatus(StrEnum):
    MATCHED = "Matched"
    NO_MATCH = "No match"
    AMBIGUOUS = "Ambiguous"
    NO_TIMESTAMP = "No timestamp"
    ALREADY_ASSIGNED = "Already assigned"


@dataclass(frozen=True)
class PhotoTrackMatchResult:
    status: PhotoTrackMatchStatus
    track_uuid: UUID | None = None
    time_delta_seconds: float | None = None
    distance_meters: float | None = None
    candidate_count: int = 0
    reason: str = ""
