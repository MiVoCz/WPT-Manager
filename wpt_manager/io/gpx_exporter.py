from pathlib import Path
from uuid import UUID

from wpt_manager.database.database import Database

from .gpx_writer import save_gpx


def export_collection_gpx(
    database: Database,
    collection_id: UUID,
    path: str | Path,
) -> None:
    collection = database.get_collection(collection_id)
    if collection is None:
        raise ValueError(f"Collection does not exist: {collection_id}")

    waypoints = database.list_waypoints(collection_id)
    save_gpx(waypoints, path)
