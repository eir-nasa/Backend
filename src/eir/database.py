"""SQLite connection and transactional, ordered schema migrations."""

import sqlite3
from collections.abc import Callable

Migration = Callable[[sqlite3.Connection], None]


def _initial_schema(connection: sqlite3.Connection) -> None:
    # Reserve the initial version for foundation metadata; feature tables belong
    # to the migrations that introduce those features.
    connection.execute("CREATE TABLE eir_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def _auth_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE auth_accounts (
        user_id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL UNIQUE,
        username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL, mission_id TEXT NOT NULL,
        profile_version INTEGER NOT NULL CHECK (profile_version >= 1)
    )""")
    connection.execute("""CREATE TABLE auth_sessions (
        session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_accounts(user_id),
        device_id TEXT NOT NULL, signing_key BLOB, refresh_hash TEXT UNIQUE,
        refresh_expires_at INTEGER
    )""")


def _health_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE health_records (
        record_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES auth_accounts(user_id),
        record_json TEXT NOT NULL, received_at TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX health_records_owner_id ON health_records (owner_id, record_id)")


def _wellbeing_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE wellbeing_checkins (
        record_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES auth_accounts(user_id),
        record_json TEXT NOT NULL, received_at TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX wellbeing_checkins_owner_id ON wellbeing_checkins (owner_id, record_id)")


def _alerts_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE risk_alerts (
        alert_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES auth_accounts(user_id),
        alert_json TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX risk_alerts_owner_id ON risk_alerts (owner_id, alert_id)")


MIGRATIONS: tuple[Migration, ...] = (
    _initial_schema, _auth_schema, _health_schema, _wellbeing_schema, _alerts_schema,
)


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
