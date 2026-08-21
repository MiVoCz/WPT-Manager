from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Waypoint:
    name: str
    latitude: float
    longitude: float

    id: UUID = field(default_factory=uuid4)

    icon: str = "marker"
    color: str = "#FF0000"
    background: str = "circle"

    note: str = ""
    comment: str = ""