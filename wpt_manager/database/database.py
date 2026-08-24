import sqlite3
from pathlib import Path


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
