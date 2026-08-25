import sqlite3
from pathlib import Path
from uuid import UUID

from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS waypoints (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    icon TEXT NOT NULL,
                    color TEXT NOT NULL,
                    background TEXT NOT NULL,
                    note TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    FOREIGN KEY (collection_id)
                        REFERENCES collections(id) ON DELETE CASCADE
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

    def save_collection(self, collection: Collection) -> None:
        connection = self._connect()
        try:
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
            connection.commit()
        finally:
            connection.close()

    def get_collection(self, collection_id: UUID) -> Collection | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT id, name, description, source, source_file
                FROM collections
                WHERE id = ?
                """,
                (str(collection_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return Collection(
            id=UUID(row[0]),
            name=row[1],
            description=row[2],
            source=row[3],
            source_file=row[4],
        )

    def list_collections(self) -> list[Collection]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, name, description, source, source_file
                FROM collections
                ORDER BY created_at ASC, rowid ASC
                """
            ).fetchall()
        finally:
            connection.close()

        return [
            Collection(
                id=UUID(row[0]),
                name=row[1],
                description=row[2],
                source=row[3],
                source_file=row[4],
            )
            for row in rows
        ]

    def update_collection(self, collection: Collection) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE collections
                SET name = ?,
                    description = ?,
                    source = ?,
                    source_file = ?
                WHERE id = ?
                """,
                (
                    collection.name,
                    collection.description,
                    collection.source,
                    collection.source_file,
                    str(collection.id),
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Collection does not exist: {collection.id}"
                )
            connection.commit()
        finally:
            connection.close()

    def delete_collection(self, collection_id: UUID) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM collections WHERE id = ?",
                (str(collection_id),),
            )
            connection.commit()
        finally:
            connection.close()

    def save_waypoint(
        self,
        waypoint: Waypoint,
        collection_id: UUID,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
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
                (
                    str(waypoint.id),
                    str(collection_id),
                    waypoint.name,
                    waypoint.latitude,
                    waypoint.longitude,
                    waypoint.icon,
                    waypoint.color,
                    waypoint.background,
                    waypoint.note,
                    waypoint.comment,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def get_waypoint(self, waypoint_id: UUID) -> Waypoint | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT id,
                       name,
                       latitude,
                       longitude,
                       icon,
                       color,
                       background,
                       note,
                       comment
                FROM waypoints
                WHERE id = ?
                """,
                (str(waypoint_id),),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return Waypoint(
            id=UUID(row[0]),
            name=row[1],
            latitude=row[2],
            longitude=row[3],
            icon=row[4],
            color=row[5],
            background=row[6],
            note=row[7],
            comment=row[8],
        )

    def list_waypoints(self, collection_id: UUID) -> list[Waypoint]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id,
                       name,
                       latitude,
                       longitude,
                       icon,
                       color,
                       background,
                       note,
                       comment
                FROM waypoints
                WHERE collection_id = ?
                ORDER BY rowid ASC
                """,
                (str(collection_id),),
            ).fetchall()
        finally:
            connection.close()

        return [
            Waypoint(
                id=UUID(row[0]),
                name=row[1],
                latitude=row[2],
                longitude=row[3],
                icon=row[4],
                color=row[5],
                background=row[6],
                note=row[7],
                comment=row[8],
            )
            for row in rows
        ]

    def update_waypoint(self, waypoint: Waypoint) -> None:
        connection = self._connect()
        try:
            self._update_waypoint(connection, waypoint)
            connection.commit()
        finally:
            connection.close()

    def update_waypoints(self, waypoints: list[Waypoint]) -> None:
        connection = self._connect()
        try:
            for waypoint in waypoints:
                self._update_waypoint(connection, waypoint)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _update_waypoint(
        connection: sqlite3.Connection,
        waypoint: Waypoint,
    ) -> None:
        cursor = connection.execute(
                """
                UPDATE waypoints
                SET name = ?,
                    latitude = ?,
                    longitude = ?,
                    icon = ?,
                    color = ?,
                    background = ?,
                    note = ?,
                    comment = ?
                WHERE id = ?
                """,
                (
                    waypoint.name,
                    waypoint.latitude,
                    waypoint.longitude,
                    waypoint.icon,
                    waypoint.color,
                    waypoint.background,
                    waypoint.note,
                    waypoint.comment,
                    str(waypoint.id),
                ),
            )
        if cursor.rowcount == 0:
            raise ValueError(
                f"Waypoint does not exist: {waypoint.id}"
            )

    def delete_waypoint(self, waypoint_id: UUID) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM waypoints WHERE id = ?",
                (str(waypoint_id),),
            )
            connection.commit()
        finally:
            connection.close()
