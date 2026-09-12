from datetime import datetime, timezone

import pytest

from wpt_manager.database.database import Database
from wpt_manager.photos.import_service import (
    create_photo_from_source_item, import_source_items,
)
from wpt_manager.photos.source import PhotoSourceError, PhotoSourceItem


class FakeSource:
    source_type = "local"

    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    def list_photos(self):
        if self.error:
            raise self.error
        return self.items

    def get_photo_metadata(self, external_id):
        return {}

    def get_thumbnail(self, item):
        return item.thumbnail_url

    def get_original_reference(self, item):
        return item.source_url


def test_source_item_mapping_with_metadata_and_optional_values():
    taken = datetime(2026, 1, 2, tzinfo=timezone.utc)
    item = PhotoSourceItem(
        "42", "Photo", taken, 50.0, 14.0, None,
        "original", None, {"provider": "value"},
    )
    photo = create_photo_from_source_item(item, "local")
    assert photo.external_id == "42"
    assert photo.taken_at == taken
    assert (photo.latitude, photo.longitude, photo.altitude) == (50.0, 14.0, None)
    assert photo.thumbnail_url is None
    assert photo.track_uuid is None


def test_fake_source_list_import_duplicate_and_provider_error(tmp_path):
    database = Database(tmp_path / "source.db")
    database.initialize()
    item = PhotoSourceItem("stable", "Photo")
    source = FakeSource([item])
    assert len(import_source_items(database, source)) == 1
    assert import_source_items(database, source) == []
    with pytest.raises(PhotoSourceError):
        import_source_items(database, FakeSource(error=PhotoSourceError("failed")))
