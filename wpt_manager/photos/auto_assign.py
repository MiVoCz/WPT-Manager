from collections import Counter
from dataclasses import replace
from uuid import UUID

from wpt_manager.database.database import Database
from wpt_manager.models.photo import Photo
from wpt_manager.models.photo_track_match import PhotoTrackMatchResult, PhotoTrackMatchStatus
from wpt_manager.photos.photo_track_matcher import PhotoTrackMatcher


def preview_photo_matches(
    photos: list[Photo], matcher: PhotoTrackMatcher, *, overwrite_existing: bool = False,
) -> dict[UUID, PhotoTrackMatchResult]:
    return {
        photo.id: (
            PhotoTrackMatchResult(PhotoTrackMatchStatus.ALREADY_ASSIGNED,
                                  reason="Existing assignment is preserved.")
            if photo.track_uuid is not None and not overwrite_existing
            else matcher.match_photo(photo)
        ) for photo in photos
    }


def match_summary(results: dict[UUID, PhotoTrackMatchResult]) -> str:
    counts = Counter(result.status for result in results.values())
    return "\n".join([
        f"Photos scanned: {len(results)}",
        *(f"{status.value}: {counts[status]}" for status in PhotoTrackMatchStatus),
    ])


def apply_photo_matches(
    database: Database, results: dict[UUID, PhotoTrackMatchResult], *,
    overwrite_existing: bool = False,
) -> int:
    applied = 0
    for photo_id, result in results.items():
        if result.status != PhotoTrackMatchStatus.MATCHED or result.track_uuid is None:
            continue
        # Re-read to preserve current descriptions/GPS and assignments made since preview.
        photo = database.get_photo(photo_id)
        if photo is None or (photo.track_uuid is not None and not overwrite_existing):
            continue
        database.update_photo(replace(photo, track_uuid=result.track_uuid))
        applied += 1
    return applied


def auto_assign_photos(
    database: Database, photos: list[Photo], matcher: PhotoTrackMatcher, *,
    overwrite_existing: bool = False,
) -> dict[UUID, PhotoTrackMatchResult]:
    results = preview_photo_matches(photos, matcher, overwrite_existing=overwrite_existing)
    apply_photo_matches(database, results, overwrite_existing=overwrite_existing)
    return results
