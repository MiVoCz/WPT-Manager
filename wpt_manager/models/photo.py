from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class Photo:
    name: str
    source_type: str
    id: UUID = field(default_factory=uuid4)
    track_uuid: UUID | None = None
    taken_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    source_url: str | None = None
    thumbnail_url: str | None = None
    external_id: str | None = None
    description: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
