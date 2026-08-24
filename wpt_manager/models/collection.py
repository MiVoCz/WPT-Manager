from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class Collection:
    name: str

    id: UUID = field(default_factory=uuid4)

    description: str = ""
    source: str = ""
    source_file: str = ""
