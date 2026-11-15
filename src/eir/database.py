"""SQLite connection and transactional, ordered schema migrations."""

import sqlite3
from collections.abc import Callable

Migration = Callable[[sqlite3.Connection], None]


def _initial_schema(connection: sqlite3.Connection) -> None:
    # Reserve the initial version for foundation metadata; feature tables belong
    # to the migrations that introduce those features.
    connection.execute("CREATE TABLE eir_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


MIGRATIONS: tuple[Migration, ...] = (_initial_schema,)


def migrate(connection: sqlite3.Connection) -> None:
    """Apply pending migrations atomically, refusing unknown future versions."""
    try:
        connection.execute("BEGIN EXCLUSIVE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError(f"Unsupported database schema version: {version}")
        for index in range(version, len(MIGRATIONS)):
            MIGRATIONS[index](connection)
            connection.execute(f"PRAGMA user_version = {index + 1}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def open_database(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        migrate(connection)
    except BaseException:
        connection.close()
        raise
    return connection
