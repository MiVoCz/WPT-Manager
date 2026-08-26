from pathlib import Path

from wpt_manager.database.database import Database
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint

from .gpx_reader import load_gpx


def import_gpx(
    database: Database,
    path: str | Path,
    collection_name: str,
    description: str = "",
) -> Collection:
    source_path = Path(path)
    waypoints = load_gpx(source_path)
    return import_waypoints(
        database,
        waypoints,
        collection_name,
        source_path.name,
        description,
    )


def import_waypoints(
    database: Database,
    waypoints: list[Waypoint],
    collection_name: str,
    source_file: str,
    description: str = "",
) -> Collection:
    collection = Collection(
        name=collection_name,
        description=description,
        source="mapy.com",
        source_file=source_file,
    )

    connection = database._connect()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO collections (
                    id,
                    name,
                    description,
                    source,
                    source_file
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(collection.id),
                    collection.name,
                    collection.description,
                    collection.source,
                    collection.source_file,
                ),
            )

            connection.executemany(
                """
                INSERT INTO waypoints (
                    id,
                    collection_id,
                    name,
                    latitude,
                    longitude,
                    icon,
                    color,
                    background,
                    note,
                    comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(waypoint.id),
                        str(collection.id),
                        waypoint.name,
                        waypoint.latitude,
                        waypoint.longitude,
                        waypoint.icon,
                        waypoint.color,
                        waypoint.background,
                        waypoint.note,
                        waypoint.comment,
                    )
                    for waypoint in waypoints
                ],
            )
    finally:
        connection.close()

    return collection
