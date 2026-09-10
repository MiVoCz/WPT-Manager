from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass
class Adventure:
    name: str
    uuid: UUID = field(default_factory=uuid4)
    description: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def id(self) -> UUID:
        return self.uuid
