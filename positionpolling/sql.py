"""SQL-related constants and utilities."""
import sqlite3
from pathlib import Path

SQL_CREATE_PLAYER_POSITIONS_TABLE: str = 'CREATE TABLE IF NOT EXISTS player_positions(' \
    + 'timestamp REAL, ' \
    + 'player_uuid TEXT, ' \
    + 'world TEXT, ' \
    + 'x INTEGER, ' \
    + 'y INTEGER, ' \
    + 'z INTEGER' \
    + ');'
"""Statement string used to create the ``player_positions`` SQL table if it does not exist."""

SQL_INSERT_INTO_PLAYER_POSITIONS: str = 'INSERT INTO player_positions(' \
    + 'timestamp, ' \
    + 'player_uuid, ' \
    + 'world, ' \
    + 'x, ' \
    + 'y, ' \
    + 'z' \
    + ') VALUES(?, ?, ?, ?, ?, ?);'
"""Statement string used to insert rows into the ``player_positions`` SQL table.

Expects 6 parameters for column values.
"""

def table_exists(db: str | Path | sqlite3.Connection, table: str) -> bool:
    """Checks whether a given table exists in an SQLite database.

    The database is automatically closed if ``db`` is not an instance of :class:`sqlite3.Connection`; if it is, it is
    neither automatically opened nor closed.
    """
    is_existing_connection: bool = isinstance(db, sqlite3.Connection)

    try:
        if not is_existing_connection:
            db = sqlite3.connect(db)

        return bool(
            db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = (?);", [table]).fetchall(),
        )
    finally:
        if not is_existing_connection:
            # Only close if we just now opened it from a path
            db.close()
