from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

DEFAULT_TRACK_COLOR = "#2563EB"


@dataclass
class TrackPoint:
    latitude: float
    longitude: float
    sequence: int
    elevation: float | None = None
    time: datetime | None = None
    segment_index: int = 0


@dataclass
class Track:
    name: str
    source_file: str
    points: list[TrackPoint] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    start_time: datetime | None = None
    end_time: datetime | None = None
    distance_m: float = 0.0
    point_count: int = 0
    color: str = DEFAULT_TRACK_COLOR
