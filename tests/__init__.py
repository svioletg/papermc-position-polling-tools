import random
import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, Any
from uuid import UUID, uuid4

from geometry import Tuple4

from positionpolling.const import Y_RANGE, World
from positionpolling.models import Entry
from positionpolling.util import coerce

TESTS_DIR: Path = Path(__file__).absolute().parent
TESTS_DATA_DIR: Path = TESTS_DIR / 'data'
TESTS_DATA_TMP_DIR: Path = TESTS_DATA_DIR / 'tmp'

TESTS_DATA_DIR.mkdir(exist_ok=True)
TESTS_DATA_TMP_DIR.mkdir(exist_ok=True)

def gen_pos_logs(
        n: int,
        *,
        players: list[UUID | str] | int = 5,
        worlds: list[World] | None = None,
        bounds: Tuple4[int] = (-2000, -2000, 2000, 2000),
    ) -> list[Entry]:
    """Generates a list of ``n`` ``Entry`` objects."""
    worlds = worlds or list(World)
    playerlist = [coerce(p, UUID) for p in players] if isinstance(players, list) else [uuid4() for _ in range(players)]

    return [
        Entry(
            t,
            random.choice(playerlist),
            world := random.choice(worlds),
            random.randint(bounds[0], bounds[2]),
            random.randint(*Y_RANGE[world]),
            random.randint(bounds[1], bounds[3]),
        )
        for t in range(n)
    ]

@contextmanager
def tempdb(
        setup: str,
        data: dict[str, Sequence[tuple[Any, ...]]],
    ) -> Generator[tuple[sqlite3.Connection, IO[bytes]]]:
    """Creates a temporary SQLite database file and yields a connection to it and the file itself.

    The database is closed after yielding the connection, and the file created is automatically deleted on fixture
    exit.

    :param setup: Initial statement to execute before inserting data.
    :param data: Dictionary mapping table name strings to rows (lists) of column values to insert.
    """
    with NamedTemporaryFile('wb', dir=TESTS_DATA_TMP_DIR, delete=True, delete_on_close=False) as f:
        # sqlite3.connect() will need to open this again, and it can't be opened while open on a non-POSIX system
        f.close()

        conn = sqlite3.connect(f.name)
        curs = conn.cursor()
        curs.execute(setup)

        for table, values in data.items():
            curs.executemany(f'INSERT INTO {table} VALUES({', '.join('?' * len(values[0]))})', values)

        conn.commit()
        curs.close()

        try:
            yield conn, f
        finally:
            conn.close()
