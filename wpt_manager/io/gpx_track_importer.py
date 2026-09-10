from pathlib import Path
from uuid import UUID

from wpt_manager.database.database import Database
from wpt_manager.models.track import Track
from wpt_manager.models.adventure import Adventure

from .gpx_track_reader import load_gpx_tracks


def import_gpx_tracks(database: Database, path: str | Path) -> list[Track]:
    tracks = load_gpx_tracks(path)
    database.save_tracks(tracks)
    return tracks


def import_gpx_files(
    database: Database, paths: list[str | Path]
) -> list[Track]:
    tracks = [track for path in paths for track in load_gpx_tracks(path)]
    database.save_tracks(tracks)
    return tracks


def import_gpx_files_to_adventure(
    database: Database,
    paths: list[str | Path],
    adventure_uuid: UUID,
    *,
    new_adventure: Adventure | None = None,
) -> list[Track]:
    tracks = [
        track
        for path in paths
        for track in load_gpx_tracks(path)
    ]
    database.save_tracks_to_adventure(
        tracks, adventure_uuid, new_adventure=new_adventure
    )
    return tracks
