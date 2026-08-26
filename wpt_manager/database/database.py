import sqlite3
from pathlib import Path
from uuid import UUID

from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint


SCHEMA_VERSION = 2


class DatabaseSchemaError(RuntimeError):
    """Raised when the database schema cannot be safely opened."""


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
            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
            if version > SCHEMA_VERSION:
                raise DatabaseSchemaError(
                    "Database schema version "
                    f"{version} is newer than the supported version "
                    f"{SCHEMA_VERSION}."
                )

            connection.execute("BEGIN IMMEDIATE")
            if version == 0:
                version = self._initialize_unversioned_schema(connection)

            while version < SCHEMA_VERSION:
                if version == 1:
                    self._migrate_schema_1_to_2(connection)
                    version = 2
                else:
                    raise DatabaseSchemaError(
                        f"Unsupported database schema version: {version}."
                    )
                connection.execute(f"PRAGMA user_version = {version}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _initialize_unversioned_schema(
        connection: sqlite3.Connection,
    ) -> int:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if not tables:
            Database._create_current_schema(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            return SCHEMA_VERSION

        if not {"collections", "waypoints"}.issubset(tables):
            raise DatabaseSchemaError(
                "Unversioned database does not contain the expected schema."
            )

        waypoint_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(waypoints)"
            ).fetchall()
        }
        version = 2 if "created_at" in waypoint_columns else 1
        connection.execute(f"PRAGMA user_version = {version}")
        return version

    @staticmethod
    def _create_current_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
                CREATE TABLE collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
        )
        connection.execute(
            """
                CREATE TABLE waypoints (
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
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (collection_id)
                        REFERENCES collections(id) ON DELETE CASCADE
                )
            """
        )

    @staticmethod
    def _migrate_schema_1_to_2(
        connection: sqlite3.Connection,
    ) -> None:
        connection.execute(
            """
            CREATE TABLE waypoints_new (
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (collection_id)
                    REFERENCES collections(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            INSERT INTO waypoints_new (
                id, collection_id, name, latitude, longitude,
                icon, color, background, note, comment, created_at
            )
            SELECT id, collection_id, name, latitude, longitude,
                   icon, color, background, note, comment,
                   CURRENT_TIMESTAMP
            FROM waypoints
            """
        )
        connection.execute("DROP TABLE waypoints")
        connection.execute(
            "ALTER TABLE waypoints_new RENAME TO waypoints"
        )

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
                ORDER BY name COLLATE NOCASE ASC, id ASC
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

    def list_waypoints(
        self,
        collection_id: UUID,
        sort_by: str = "name",
    ) -> list[Waypoint]:
        order_by = {
            "name": "name COLLATE NOCASE ASC, id ASC",
            "created_at": "created_at ASC, id ASC",
        }.get(sort_by)
        if order_by is None:
            raise ValueError(f"Unsupported waypoint sort: {sort_by}")

        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
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
                ORDER BY {order_by}
                """,  # nosec B608: order_by comes from the fixed map above
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

    def delete_waypoints(self, waypoint_ids: list[UUID]) -> None:
        if not waypoint_ids:
            return

        connection = self._connect()
        try:
            for waypoint_id in waypoint_ids:
                connection.execute(
                    "DELETE FROM waypoints WHERE id = ?",
                    (str(waypoint_id),),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
