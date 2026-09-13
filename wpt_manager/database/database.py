import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.photo import Photo


SCHEMA_VERSION = 7


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
                elif version == 2:
                    self._migrate_schema_2_to_3(connection)
                    version = 3
                elif version == 3:
                    self._migrate_schema_3_to_4(connection)
                    version = 4
                elif version == 4:
                    self._migrate_schema_4_to_5(connection)
                    version = 5
                elif version == 5:
                    self._migrate_schema_5_to_6(connection)
                    version = 6
                elif version == 6:
                    self._migrate_schema_6_to_7(connection)
                    version = 7
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
        if {"tracks", "track_points"}.issubset(tables):
            track_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(tracks)"
                ).fetchall()
            }
            if "color" not in track_columns:
                version = 3
            else:
                point_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(track_points)"
                    ).fetchall()
                }
                if "segment_index" not in point_columns:
                    version = 4
                else:
                    if "adventures" not in tables:
                        version = 5
                    else:
                        version = 7 if "photos" in tables else 6
        else:
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
        Database._create_track_tables(connection)
        Database._create_adventure_tables(connection)
        Database._create_photo_table(connection)

    @staticmethod
    def _create_photo_table(connection: sqlite3.Connection) -> None:
        """Create current Photos schema; historical migrations must not call this."""
        Database._create_photo_table_v7(connection)

    @staticmethod
    def _create_photo_table_v7(connection: sqlite3.Connection) -> None:
        """Frozen schema v7 definition, including its original index and FK."""
        connection.execute(
            """
            CREATE TABLE photos (
                uuid TEXT PRIMARY KEY,
                track_uuid TEXT,
                name TEXT NOT NULL,
                taken_at TEXT,
                latitude REAL,
                longitude REAL,
                altitude REAL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                thumbnail_url TEXT,
                external_id TEXT,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (track_uuid) REFERENCES tracks(id)
                    ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX photos_source_external_id "
            "ON photos(source_type, external_id) WHERE external_id IS NOT NULL"
        )

    @staticmethod
    def _create_adventure_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE adventures (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE adventure_tracks (
                adventure_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                PRIMARY KEY (adventure_uuid, track_uuid),
                FOREIGN KEY (adventure_uuid) REFERENCES adventures(uuid)
                    ON DELETE CASCADE,
                FOREIGN KEY (track_uuid) REFERENCES tracks(id)
                    ON DELETE CASCADE
            )
            """
        )

    @staticmethod
    def _create_track_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE tracks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_file TEXT NOT NULL,
                created_at TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                distance_m REAL NOT NULL,
                point_count INTEGER NOT NULL,
                color TEXT NOT NULL DEFAULT '#2563EB'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE track_points (
                track_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                elevation REAL,
                time TEXT,
                segment_index INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (track_id, sequence),
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
            """
        )

    @staticmethod
    def _migrate_schema_2_to_3(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE tracks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_file TEXT NOT NULL,
                created_at TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                distance_m REAL NOT NULL,
                point_count INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE track_points (
                track_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                elevation REAL,
                time TEXT,
                PRIMARY KEY (track_id, sequence),
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
            """
        )

    @staticmethod
    def _migrate_schema_3_to_4(connection: sqlite3.Connection) -> None:
        connection.execute(
            "ALTER TABLE tracks ADD COLUMN color TEXT NOT NULL "
            "DEFAULT '#2563EB'"
        )

    @staticmethod
    def _migrate_schema_4_to_5(connection: sqlite3.Connection) -> None:
        connection.execute(
            "ALTER TABLE track_points ADD COLUMN segment_index "
            "INTEGER NOT NULL DEFAULT 0"
        )

    @staticmethod
    def _migrate_schema_5_to_6(connection: sqlite3.Connection) -> None:
        Database._create_adventure_tables(connection)

    @staticmethod
    def _migrate_schema_6_to_7(connection: sqlite3.Connection) -> None:
        Database._create_photo_table_v7(connection)

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

    def get_waypoint_collection_id(self, waypoint_id: UUID) -> UUID | None:
        """Return the owning Collection independently of the current GUI selection."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT collection_id FROM waypoints WHERE id = ?",
                (str(waypoint_id),),
            ).fetchone()
        finally:
            connection.close()
        return UUID(row[0]) if row is not None else None

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

    def move_waypoints(
        self,
        waypoint_ids: list[UUID],
        target_collection_id: UUID,
    ) -> None:
        unique_ids = list(dict.fromkeys(waypoint_ids))
        if not unique_ids:
            return
        connection = self._connect()
        try:
            target_exists = connection.execute(
                "SELECT 1 FROM collections WHERE id = ?",
                (str(target_collection_id),),
            ).fetchone()
            if target_exists is None:
                raise ValueError(
                    f"Target Collection does not exist: {target_collection_id}"
                )

            placeholders = ", ".join("?" for _ in unique_ids)
            rows = connection.execute(
                f"SELECT id, collection_id FROM waypoints "
                f"WHERE id IN ({placeholders})",  # nosec B608
                tuple(str(waypoint_id) for waypoint_id in unique_ids),
            ).fetchall()
            collections_by_waypoint = {
                UUID(waypoint_id): UUID(collection_id)
                for waypoint_id, collection_id in rows
            }
            missing_ids = [
                waypoint_id
                for waypoint_id in unique_ids
                if waypoint_id not in collections_by_waypoint
            ]
            if missing_ids:
                raise ValueError(f"Waypoint does not exist: {missing_ids[0]}")
            if any(
                source_id == target_collection_id
                for source_id in collections_by_waypoint.values()
            ):
                raise ValueError(
                    "Target Collection must differ from the source Collection."
                )

            source_ids = set(collections_by_waypoint.values())
            source_placeholders = ", ".join("?" for _ in source_ids)
            source_count = connection.execute(
                f"SELECT COUNT(*) FROM collections "
                f"WHERE id IN ({source_placeholders})",  # nosec B608
                tuple(str(source_id) for source_id in source_ids),
            ).fetchone()[0]
            if source_count != len(source_ids):
                raise ValueError("Source Collection does not exist.")

            connection.execute(
                f"UPDATE waypoints SET collection_id = ? "
                f"WHERE id IN ({placeholders})",  # nosec B608
                (
                    str(target_collection_id),
                    *(str(waypoint_id) for waypoint_id in unique_ids),
                ),
            )
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

    @staticmethod
    def _datetime_text(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _track_from_row(row: tuple) -> Track:
        return Track(
            id=UUID(row[0]),
            name=row[1],
            source_file=row[2],
            created_at=datetime.fromisoformat(row[3]),
            start_time=datetime.fromisoformat(row[4]) if row[4] else None,
            end_time=datetime.fromisoformat(row[5]) if row[5] else None,
            distance_m=row[6],
            point_count=row[7],
            color=row[8],
        )

    def save_track(self, track: Track) -> None:
        self.save_tracks([track])

    def save_tracks(self, tracks: list[Track]) -> None:
        connection = self._connect()
        try:
            with connection:
                for track in tracks:
                    self._insert_track(connection, track)
        finally:
            connection.close()

    def _insert_track(
        self, connection: sqlite3.Connection, track: Track
    ) -> None:
        connection.execute(
                        """
                        INSERT INTO tracks (
                            id, name, source_file, created_at, start_time,
                            end_time, distance_m, point_count, color
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(track.id), track.name, track.source_file,
                            self._datetime_text(track.created_at),
                            self._datetime_text(track.start_time),
                            self._datetime_text(track.end_time),
                            track.distance_m, track.point_count, track.color,
                        ),
        )
        connection.executemany(
                        """
                        INSERT INTO track_points (
                            track_id, sequence, latitude, longitude,
                            elevation, time, segment_index
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                str(track.id), point.sequence,
                                point.latitude, point.longitude,
                                point.elevation,
                                self._datetime_text(point.time),
                                point.segment_index,
                            )
                            for point in track.points
                        ],
        )

    def save_tracks_to_adventure(
        self,
        tracks: list[Track],
        adventure_uuid: UUID,
        new_adventure: Adventure | None = None,
    ) -> None:
        connection = self._connect()
        try:
            with connection:
                if new_adventure is not None:
                    connection.execute(
                        "INSERT INTO adventures "
                        "(uuid, name, description, created_at) VALUES (?, ?, ?, ?)",
                        (str(new_adventure.uuid), new_adventure.name,
                         new_adventure.description,
                         self._datetime_text(new_adventure.created_at)),
                    )
                next_sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 "
                    "FROM adventure_tracks WHERE adventure_uuid = ?",
                    (str(adventure_uuid),),
                ).fetchone()[0]
                for offset, track in enumerate(tracks):
                    self._insert_track(connection, track)
                    connection.execute(
                        "INSERT INTO adventure_tracks "
                        "(adventure_uuid, track_uuid, sequence) VALUES (?, ?, ?)",
                        (str(adventure_uuid), str(track.id), next_sequence + offset),
                    )
        finally:
            connection.close()

    def get_track(self, track_id: UUID) -> Track | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, name, source_file, created_at, start_time, "
                "end_time, distance_m, point_count, color FROM tracks WHERE id = ?",
                (str(track_id),),
            ).fetchone()
        finally:
            connection.close()
        return self._track_from_row(row) if row is not None else None

    def list_tracks(self) -> list[Track]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, name, source_file, created_at, start_time, "
                "end_time, distance_m, point_count, color FROM tracks "
                "ORDER BY created_at DESC, name COLLATE NOCASE ASC"
            ).fetchall()
        finally:
            connection.close()
        return [self._track_from_row(row) for row in rows]

    def update_track(self, track: Track) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE tracks SET name = ?, color = ? WHERE id = ?",
                (track.name, track.color, str(track.id)),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Track does not exist: {track.id}")
            connection.commit()
        finally:
            connection.close()

    def delete_track(self, track_id: UUID) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM tracks WHERE id = ?", (str(track_id),))
            connection.commit()
        finally:
            connection.close()

    def list_track_points(self, track_id: UUID) -> list[TrackPoint]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT latitude, longitude, sequence, elevation, time, "
                "segment_index "
                "FROM track_points WHERE track_id = ? ORDER BY sequence",
                (str(track_id),),
            ).fetchall()
        finally:
            connection.close()
        return [
            TrackPoint(
                latitude=row[0], longitude=row[1], sequence=row[2],
                elevation=row[3],
                time=datetime.fromisoformat(row[4]) if row[4] else None,
                segment_index=row[5],
            )
            for row in rows
        ]

    def save_adventure(self, adventure: Adventure) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO adventures (uuid, name, description, created_at) "
                "VALUES (?, ?, ?, ?)",
                (str(adventure.uuid), adventure.name, adventure.description,
                 self._datetime_text(adventure.created_at)),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _adventure_from_row(row: tuple) -> Adventure:
        return Adventure(
            uuid=UUID(row[0]), name=row[1], description=row[2] or "",
            created_at=datetime.fromisoformat(row[3]),
        )

    def get_adventure(self, adventure_uuid: UUID) -> Adventure | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT uuid, name, description, created_at FROM adventures "
                "WHERE uuid = ?", (str(adventure_uuid),),
            ).fetchone()
        finally:
            connection.close()
        return self._adventure_from_row(row) if row else None

    def list_adventures(self) -> list[Adventure]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT uuid, name, description, created_at FROM adventures "
                "ORDER BY name COLLATE NOCASE, uuid"
            ).fetchall()
        finally:
            connection.close()
        return [self._adventure_from_row(row) for row in rows]

    def update_adventure(self, adventure: Adventure) -> None:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE adventures SET name = ?, description = ? WHERE uuid = ?",
                (adventure.name, adventure.description, str(adventure.uuid)),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Adventure does not exist: {adventure.uuid}")
            connection.commit()
        finally:
            connection.close()

    def delete_adventure(self, adventure_uuid: UUID) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM adventures WHERE uuid = ?", (str(adventure_uuid),)
            )
            connection.commit()
        finally:
            connection.close()

    def add_track_to_adventure(
        self, adventure_uuid: UUID, track_uuid: UUID
    ) -> None:
        connection = self._connect()
        try:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM adventure_tracks "
                "WHERE adventure_uuid = ?", (str(adventure_uuid),),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO adventure_tracks "
                "(adventure_uuid, track_uuid, sequence) VALUES (?, ?, ?)",
                (str(adventure_uuid), str(track_uuid), sequence),
            )
            connection.commit()
        finally:
            connection.close()

    def add_tracks_to_adventure(
        self, adventure_uuid: UUID, track_uuids: list[UUID]
    ) -> None:
        unique_ids = list(dict.fromkeys(track_uuids))
        connection = self._connect()
        try:
            with connection:
                existing = {
                    UUID(row[0]) for row in connection.execute(
                        "SELECT track_uuid FROM adventure_tracks "
                        "WHERE adventure_uuid = ?", (str(adventure_uuid),)
                    ).fetchall()
                }
                next_sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), -1) + 1 "
                    "FROM adventure_tracks WHERE adventure_uuid = ?",
                    (str(adventure_uuid),),
                ).fetchone()[0]
                for track_uuid in unique_ids:
                    if track_uuid in existing:
                        continue
                    connection.execute(
                        "INSERT INTO adventure_tracks "
                        "(adventure_uuid, track_uuid, sequence) VALUES (?, ?, ?)",
                        (str(adventure_uuid), str(track_uuid), next_sequence),
                    )
                    next_sequence += 1
        finally:
            connection.close()

    def remove_track_from_adventure(
        self, adventure_uuid: UUID, track_uuid: UUID
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM adventure_tracks WHERE adventure_uuid = ? "
                "AND track_uuid = ?", (str(adventure_uuid), str(track_uuid)),
            )
            connection.commit()
        finally:
            connection.close()

    def list_adventure_tracks(self, adventure_uuid: UUID) -> list[Track]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT t.id, t.name, t.source_file, t.created_at, t.start_time, "
                "t.end_time, t.distance_m, t.point_count, t.color FROM tracks t "
                "JOIN adventure_tracks a ON a.track_uuid = t.id "
                "WHERE a.adventure_uuid = ? ORDER BY a.sequence, t.id",
                (str(adventure_uuid),),
            ).fetchall()
        finally:
            connection.close()
        return [self._track_from_row(row) for row in rows]

    def list_track_adventure_memberships(
        self,
    ) -> dict[UUID, list[Adventure]]:
        memberships: dict[UUID, list[Adventure]] = {}
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT at.track_uuid, a.uuid, a.name, a.description, "
                "a.created_at FROM adventure_tracks at "
                "JOIN adventures a ON a.uuid = at.adventure_uuid "
                "ORDER BY a.name COLLATE NOCASE, a.uuid"
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            memberships.setdefault(UUID(row[0]), []).append(
                self._adventure_from_row(row[1:])
            )
        return memberships

    def set_adventure_track_order(
        self, adventure_uuid: UUID, track_uuids: list[UUID]
    ) -> None:
        connection = self._connect()
        try:
            with connection:
                existing = {
                    UUID(row[0]) for row in connection.execute(
                        "SELECT track_uuid FROM adventure_tracks "
                        "WHERE adventure_uuid = ?", (str(adventure_uuid),)
                    ).fetchall()
                }
                if len(track_uuids) != len(set(track_uuids)) or set(track_uuids) != existing:
                    raise ValueError("Track order must contain every Adventure track once.")
                for sequence, track_uuid in enumerate(track_uuids):
                    connection.execute(
                        "UPDATE adventure_tracks SET sequence = ? "
                        "WHERE adventure_uuid = ? AND track_uuid = ?",
                        (sequence, str(adventure_uuid), str(track_uuid)),
                    )
        finally:
            connection.close()

    @staticmethod
    def _photo_from_row(row: tuple) -> Photo:
        return Photo(
            id=UUID(row[0]),
            track_uuid=UUID(row[1]) if row[1] else None,
            name=row[2],
            taken_at=datetime.fromisoformat(row[3]) if row[3] else None,
            latitude=row[4],
            longitude=row[5],
            altitude=row[6],
            source_type=row[7],
            source_url=row[8],
            thumbnail_url=row[9],
            external_id=row[10],
            description=row[11],
            created_at=datetime.fromisoformat(row[12]),
        )

    @staticmethod
    def _photo_columns() -> str:
        return (
            "uuid, track_uuid, name, taken_at, latitude, longitude, altitude, "
            "source_type, source_url, thumbnail_url, external_id, description, "
            "created_at"
        )

    def save_photo(self, photo: Photo) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO photos (" + self._photo_columns() + ") "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._photo_values(photo),
            )
            connection.commit()
        finally:
            connection.close()

    @classmethod
    def _photo_values(cls, photo: Photo) -> tuple:
        return (
            str(photo.id),
            str(photo.track_uuid) if photo.track_uuid else None,
            photo.name,
            cls._datetime_text(photo.taken_at),
            photo.latitude,
            photo.longitude,
            photo.altitude,
            photo.source_type,
            photo.source_url,
            photo.thumbnail_url,
            photo.external_id,
            photo.description,
            cls._datetime_text(photo.created_at),
        )

    def update_photo(self, photo: Photo) -> None:
        connection = self._connect()
        try:
            values = self._photo_values(photo)
            cursor = connection.execute(
                "UPDATE photos SET track_uuid = ?, name = ?, taken_at = ?, "
                "latitude = ?, longitude = ?, altitude = ?, source_type = ?, "
                "source_url = ?, thumbnail_url = ?, external_id = ?, "
                "description = ?, created_at = ? WHERE uuid = ?",
                (*values[1:], values[0]),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Photo does not exist: {photo.id}")
            connection.commit()
        finally:
            connection.close()

    def set_photos_track(self, photo_uuids: list[UUID], track_uuid: UUID | None) -> int:
        """Change only Track assignment, atomically for all existing selected Photos."""
        connection = self._connect()
        try:
            with connection:
                cursor = connection.executemany(
                    "UPDATE photos SET track_uuid = ? WHERE uuid = ?",
                    [(str(track_uuid) if track_uuid is not None else None, str(photo_id))
                     for photo_id in dict.fromkeys(photo_uuids)],
                )
            return cursor.rowcount
        finally:
            connection.close()

    def get_photo(self, photo_uuid: UUID) -> Photo | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT " + self._photo_columns() + " FROM photos WHERE uuid = ?",
                (str(photo_uuid),),
            ).fetchone()
        finally:
            connection.close()
        return self._photo_from_row(row) if row else None

    def list_photos(self) -> list[Photo]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT " + self._photo_columns() + " FROM photos "
                "ORDER BY COALESCE(taken_at, created_at) DESC, name COLLATE NOCASE"
            ).fetchall()
        finally:
            connection.close()
        return [self._photo_from_row(row) for row in rows]

    def delete_photo(self, photo_uuid: UUID) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM photos WHERE uuid = ?", (str(photo_uuid),)
            )
            connection.commit()
        finally:
            connection.close()

    def list_photos_for_track(self, track_uuid: UUID) -> list[Photo]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT " + self._photo_columns() + " FROM photos "
                "WHERE track_uuid = ? ORDER BY COALESCE(taken_at, created_at), uuid",
                (str(track_uuid),),
            ).fetchall()
        finally:
            connection.close()
        return [self._photo_from_row(row) for row in rows]

    def list_standalone_photos(self) -> list[Photo]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT " + self._photo_columns() + " FROM photos "
                "WHERE track_uuid IS NULL ORDER BY COALESCE(taken_at, created_at), uuid"
            ).fetchall()
        finally:
            connection.close()
        return [self._photo_from_row(row) for row in rows]
