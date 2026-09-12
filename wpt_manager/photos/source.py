from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


class PhotoSourceError(RuntimeError):
    """Base error raised by a remote photo source."""


class PhotoAuthenticationError(PhotoSourceError):
    pass


@dataclass(frozen=True)
class PhotoSourceItem:
    external_id: str | None
    name: str
    taken_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    source_url: str | None = None
    thumbnail_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PhotoSource(Protocol):
    source_type: str

    def list_photos(self) -> list[PhotoSourceItem]: ...

    def get_photo_metadata(self, external_id: str) -> dict[str, Any]: ...

    def get_thumbnail(self, item: PhotoSourceItem) -> str | None: ...

    def get_original_reference(self, item: PhotoSourceItem) -> str | None: ...
