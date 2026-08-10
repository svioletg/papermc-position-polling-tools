"""Dataclasses and models for position polling tools."""
import sqlite3
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Self
from uuid import UUID

from geometry import Tuple4

from positionpolling.const import World


@dataclass
class Entry:
    """Represents one row of the plugin database's `player_positions` table."""

    timestamp: float
    player_uuid: UUID
    world: World
    x: float
    y: float
    z: float

    def __sub__(self, other: 'Entry') -> 'Entry':
        """Returns a new entry representing the difference between two entries.

        Fields :data:`timestamp`, :data:`x`, :data:`y`:, and :data:`z` are subtracted. The rest are left intact.
        """
        if not isinstance(other, Entry):
            return NotImplemented

        return Entry(
            self.timestamp - other.timestamp,
            self.player_uuid,
            self.world,
            self.x - other.x,
            self.y - other.y,
            self.z - other.z,
        )

    @classmethod
    def from_row(cls, row: tuple[float, str, str, float, float, float]) -> Self:
        """Returns a new :class:`Entry` created from a raw row of the `player_positions` table."""
        return cls(
            timestamp=float(row[0]),
            player_uuid=UUID(row[1]),
            world=World(row[2]),
            x=float(row[3]),
            y=float(row[4]),
            z=float(row[5]),
        )

class PlayerPositions:
    """Dataclass for using player position :class:`Entry` data."""

    entries: tuple[Entry, ...]

    def __init__(self, entries: tuple[Entry, ...] | None = None) -> None:
        self.entries = entries or ()

    def __repr__(self) -> str:  # noqa: D105
        return f'<{self.__class__.__name__}; {len(self.entries)} entries>'

    @classmethod
    def from_sql(cls, sql_db_path: str | Path) -> Self:
        """Creates an instance from an SQL database path."""
        return cls(
            entries=tuple([
                Entry.from_row(row)
                for row in sqlite3.connect(sql_db_path).cursor().execute('SELECT * FROM player_positions').fetchall()
            ]),
        )

    @cached_property
    def by_player(self) -> dict[str, list[Entry]]:
        """A dictionary of entries indexed by player UUID."""
        grouped: dict[str, list[Entry]] = {}

        for entry in self.entries:
            player = str(entry.player_uuid)
            if player not in grouped:
                grouped[player] = [entry]
            else:
                grouped[player].append(entry)

        return grouped

@dataclass(frozen=True)
class RenderOpt:
    """Visualization rendering options.

    Attributes prefixed with ``v_`` are only used when rendering a video.
    """

    progress_bar: bool = False
    """Whether to show a progress bar while rendering."""
    progress_log_interval: int = 500
    """If >0, a log is printed once every time a multiple of this value of entries is processed.

    If 0, no progress logs are printed for rendering.
    """
    world_crop: Tuple4[float] | None = None
    """A rectangle of the Minecraft world (use in-game coordinates) to crop the visualization to."""
    v_fps: int = 60
    """Framerate of the rendered video."""
    v_time_factor: float | None = 0.25
    """
    A multiplier which determines the length of the final video based on the timestamps of each position log. At
    ``1.0``, each frame last the exact duration between it and the next log, effectively showing a real-time recap of
    every movement. At ``0.5``, each frame lasts half the duration; at ``0.25``, each frame lasts a quarter of the
    duration, and so on. If 0 or ``None`` is given, timestamps are ignored and every position log gets exactly one frame
    in sequence, meaning the length of the video will depend on :data:`v_fps`.

    .. note::
        Frame duration is rounded to the closest integer after being calculated, the final duration may be slightly off
        from what would be expected.
    """

RENDER_OPT_DEFAULT = RenderOpt()
