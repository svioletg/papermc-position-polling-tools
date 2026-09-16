import random
import sqlite3
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, Any
from uuid import UUID, uuid4

from geometry import Tuple4

from positionpolling.const import VANILLA_WORLDS, Y_RANGE
from positionpolling.models import Entry, PlayerPositions
from positionpolling.util import drop_duplicates

TESTS_DIR: Path = Path(__file__).absolute().parent
TESTS_DATA_DIR: Path = TESTS_DIR / 'data'
TESTS_DATA_TMP_DIR: Path = TESTS_DATA_DIR / 'tmp'

TESTS_DATA_DIR.mkdir(exist_ok=True)
TESTS_DATA_TMP_DIR.mkdir(exist_ok=True)

UUID4_DUMMY: UUID = UUID('00000000-0000-0000-0000-000000000000')

def gen_pos_logs(
        n: int,
        *,
        players: list[str] | int = 5,
        worlds: list[str] | None = None,
        bounds: Tuple4[int] = (-2000, -2000, 2000, 2000),
    ) -> list[Entry]:
    """Generates a list of ``n`` ``Entry`` objects."""
    worlds = worlds or VANILLA_WORLDS
    playerlist = players if isinstance(players, list) else [str(uuid4()) for _ in range(players)]

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

def merge_data(
        *datasets: str | Path | Sequence[Entry] | PlayerPositions,
        players: Iterable[str] | None = None,
    ) -> list[Entry]:
    players = iter(players) if players is not None else None

    merged: list[dict[str, Any]] = []

    for n, source in enumerate(datasets):
        if isinstance(source, PlayerPositions):
            data = source.entries
        if isinstance(source, str | Path):
            data = PlayerPositions.from_sql(source).entries

        if n == 0:
            origin_xy = data[0].xy
            origin_time = data[0].timestamp
            merged = [e.to_json() for e in data]
            continue

        player = next(players) if players else None

        coord_diff = data[0].xy - origin_xy

        merged.extend(e.to_json() | {
            'timestamp': origin_time + n,
            'x': e.x + coord_diff.x,
            'z': e.y + coord_diff.y,
            'player_uuid': player or e.player_uuid,
        } for n, e in enumerate(data))

    return sorted(drop_duplicates(Entry(**e) for e in merged), key=lambda e: e.timestamp)

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
