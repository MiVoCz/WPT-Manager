import sqlite3
from pathlib import Path
from uuid import UUID

from wpt_manager.models.collection import Collection


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
