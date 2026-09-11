import sqlite3
from uuid import UUID

from wpt_manager.database.database import Database
from wpt_manager.models.photo import Photo
from wpt_manager.photos.source import PhotoSource, PhotoSourceItem


def create_photo_from_source_item(
    item: PhotoSourceItem,
    source_type: str,
    track_uuid: UUID | None = None,
) -> Photo:
    return Photo(
        name=item.name,
        source_type=source_type,
        track_uuid=track_uuid,
        taken_at=item.taken_at,
        latitude=item.latitude,
        longitude=item.longitude,
        altitude=item.altitude,
        source_url=item.source_url,
        thumbnail_url=item.thumbnail_url,
        external_id=item.external_id,
    )


def import_source_items(
    database: Database,
    source: PhotoSource,
    items: list[PhotoSourceItem] | None = None,
) -> list[Photo]:
    imported: list[Photo] = []
    for item in source.list_photos() if items is None else items:
        photo = create_photo_from_source_item(item, source.source_type)
        try:
            database.save_photo(photo)
        except sqlite3.IntegrityError:
            if item.external_id is None:
                raise
            continue
        imported.append(photo)
    return imported
