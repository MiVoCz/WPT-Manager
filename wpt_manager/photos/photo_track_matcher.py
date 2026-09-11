"""Pure time-first matching; construction indexes the track points once."""

from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from uuid import UUID

from wpt_manager.models.photo import Photo
from wpt_manager.models.photo_track_match import PhotoTrackMatchResult, PhotoTrackMatchStatus
from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.validation.waypoint_duplicates import geographic_distance_m

TRACK_TIME_MARGIN_SECONDS = 300
MAX_TIME_DELTA_SECONDS = 300
MAX_GPS_DISTANCE_METERS = 2000
AMBIGUITY_TIME_DELTA_SECONDS = 10
AMBIGUITY_GPS_DISTANCE_METERS = 100


def _utc(value: datetime | None) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _gps(latitude: float | None, longitude: float | None) -> tuple[float, float] | None:
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
               for v in (latitude, longitude)):
        return None
    if abs(latitude) > 90 or abs(longitude) > 180:
        return None
    return latitude, longitude


@dataclass(frozen=True)
class _TrackIndex:
    track_uuid: UUID
    times: list[datetime]
    points: dict[datetime, list[TrackPoint]]


class PhotoTrackMatcher:
    def __init__(self, tracks: Iterable[Track]) -> None:
        self._tracks: list[_TrackIndex] = []
        for track in tracks:
            points: dict[datetime, list[TrackPoint]] = {}
            for point in track.points:
                time = _utc(point.time)
                if time is not None:
                    points.setdefault(time, []).append(point)
            if points:
                # Actual timed points define the range, even if header times are absent/stale.
                self._tracks.append(_TrackIndex(track.id, sorted(points), points))

    def match_photo(self, photo: Photo) -> PhotoTrackMatchResult:
        time = _utc(photo.taken_at)
        if time is None:
            return PhotoTrackMatchResult(PhotoTrackMatchStatus.NO_TIMESTAMP,
                                         reason="No safely normalizable photo timestamp.")
        gps = _gps(photo.latitude, photo.longitude)
        if gps is None and (photo.latitude is not None or photo.longitude is not None):
            return PhotoTrackMatchResult(PhotoTrackMatchStatus.NO_MATCH,
                                         reason="Photo GPS is partial or invalid.")
        candidates: list[PhotoTrackMatchResult] = []
        for track in self._tracks:
            if (track.times[0] - time).total_seconds() > TRACK_TIME_MARGIN_SECONDS:
                continue
            if (time - track.times[-1]).total_seconds() > TRACK_TIME_MARGIN_SECONDS:
                continue
            index = bisect_left(track.times, time)
            neighbors = track.times[max(0, index - 1):index + 1]
            delta = min(abs((stamp - time).total_seconds()) for stamp in neighbors)
            if delta > MAX_TIME_DELTA_SECONDS:
                continue
            distance: float | None = None
            if gps is not None:
                distances: list[float] = []
                for stamp in neighbors:
                    if abs((stamp - time).total_seconds()) != delta:
                        continue
                    for point in track.points[stamp]:
                        point_gps = _gps(point.latitude, point.longitude)
                        if point_gps is not None:
                            distances.append(geographic_distance_m(*gps, *point_gps))
                if not distances or min(distances) > MAX_GPS_DISTANCE_METERS:
                    continue
                distance = min(distances)
            candidates.append(PhotoTrackMatchResult(
                PhotoTrackMatchStatus.MATCHED, track.track_uuid, delta, distance,
                reason="Nearest timed point passed time and optional GPS limits.",
            ))
        candidates.sort(key=lambda item: (
            item.time_delta_seconds, item.distance_meters if item.distance_meters is not None else 0,
            str(item.track_uuid),
        ))
        if not candidates:
            return PhotoTrackMatchResult(PhotoTrackMatchStatus.NO_MATCH,
                                         reason="No track passed time and GPS limits.")
        best = candidates[0]
        # Check all close competitors: a third candidate must not hide behind a
        # runner-up with a very different GPS distance.
        for other in candidates[1:]:
            if other.time_delta_seconds - best.time_delta_seconds > AMBIGUITY_TIME_DELTA_SECONDS:
                break
            if (gps is None or abs(other.distance_meters - best.distance_meters)
                    <= AMBIGUITY_GPS_DISTANCE_METERS):
                return PhotoTrackMatchResult(
                    PhotoTrackMatchStatus.AMBIGUOUS, None, best.time_delta_seconds,
                    best.distance_meters, len(candidates), "Multiple near-equal track candidates.",
                )
        return PhotoTrackMatchResult(
            best.status, best.track_uuid, best.time_delta_seconds, best.distance_meters,
            len(candidates), best.reason,
        )
