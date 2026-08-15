"""Dataclasses and models for position polling tools."""
import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any, Self
from uuid import UUID

from geometry import Tuple4
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationInfo

from positionpolling.const import World

type ValidatorFunc[T] = Callable[[object, ValidationInfo], T]

def vld_none_ok[T](validator: ValidatorFunc[T]) \
    -> Callable[[object, ValidationInfo], T | None]:
    """Returns a validator wrapped with a ``value is None`` check that can return ``None``."""
    def wrapped(value: object, info: ValidationInfo) -> T | None:
        if value is None:
            return None

        return validator(value, info)

    return wrapped

def vld_tuple(value: object, _info: ValidationInfo) -> tuple:
    """Attempts to coerce ``value`` to a tuple of the length described by ``info``.

    Accepted values are:
        - ``None`` (returns ``None``)
        - a comma-delimited string
        - an iterable

    :raises TypeError:
        Could not interperet ``value`` as a tuple and it is not ``None``.
    :raises ValueError:
        Tuple is not the correct length.
    """
    if isinstance(value, str):
        value = tuple(float(s) for s in value.split(','))
    elif isinstance(value, Iterable):
        value = tuple(float(i) for i in value)
    else:
        raise TypeError(f'Could not interperet value as tuple: {value!r}')

    return value

@dataclass(frozen=True)
class CliOpt:
    """For use in ``RenderOpt`` field annotations to customize its corresponding command-line argument."""

    names: list[str]
    kwargs: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
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

@dataclass(frozen=True)
class PlayerPositions:
    """Dataclass for using player position :class:`Entry` data."""

    entries: tuple[Entry, ...]

    def __repr__(self) -> str:  # noqa: D105
        return f'<{self.__class__.__name__}; {len(self.entries)} entries>'

    @classmethod
    def from_sql(cls, sql_db_path: str | Path) -> Self:
        """Creates an instance from an SQL database path."""
        conn = sqlite3.connect(sql_db_path)
        cursor = conn.cursor()

        data = cursor.execute('SELECT * FROM player_positions').fetchall()

        cursor.close()
        conn.close()

        return cls(
            entries=tuple([
                Entry.from_row(row)
                for row in data
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

class RenderOpt(BaseModel):
    """Visualization rendering options.

    Attributes prefixed with ``v_`` are only used when rendering a video.
    """

    # Pydantic setup

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)
    """:meta private:"""

    # Fields

    progress_bar: Annotated[bool, CliOpt(['--progress-bar', '-P'])] = False
    """Whether to show a progress bar while rendering."""
    progress_log_interval: int = 500
    """If >0, a log is printed once every time a multiple of this value of entries is processed.

    If 0, no progress logs are printed for rendering.
    """
    world_crop: Annotated[Tuple4[float] | None, BeforeValidator(vld_none_ok(vld_tuple))] = None
    """A rectangle of the Minecraft world (use in-game coordinates) to crop the visualization to."""
    v_fix: Annotated[bool, CliOpt(['--fix-vid'])] = True
    """Whether to use FFmpeg to reprocess the rendered video from mp4v into avc1.

    Due to licensing, ``opencv`` can't use avc1 directly, so videos are created using mp4v instead. mp4v is not fully
    supported by many browsers and other software, so the next best option is to re-process the video with FFmpeg
    (which does support encoding to avc1/H.264) after it has been initially created. This process can take some time,
    so if you know an mp4v-encoded video works fine for your needs, you can disable this for a faster render.

    .. note::
        This requires FFmpeg to be installed; it does not come bundled with this package.
    """
    v_fps: Annotated[int, CliOpt(['--fps'])] = 60
    """Framerate of the rendered video."""
    v_time_factor: Annotated[float, CliOpt(['--time-factor', '-t'])] = 0.25
    """
    A multiplier which determines the length of the final video based on the timestamps of each position log. At
    ``1.0``, each frame last the exact duration between it and the next log, effectively showing a real-time recap of
    every movement. At ``0.5``, each frame lasts half the duration; at ``0.25``, each frame lasts a quarter of the
    duration, and so on. If 0, timestamps are ignored and every position log gets exactly one frame in sequence, meaning
    the length of the video will depend on :data:`v_fps`.

    .. note::
        Frame duration is rounded to the closest integer after being calculated, the final duration may be slightly off
        from what would be expected.
    """

    @classmethod
    def from_json(cls, fp: str | Path) -> Self:
        """Returns a ``RenderOpt`` created from the contents of a JSON file."""
        fp = Path(fp)

        if not fp.is_file():
            raise FileNotFoundError(f'Not a file or does not exist: {fp}')

        with open(fp, 'r', encoding='utf-8') as f:
            content = json.load(f)

        return cls(**content)

    def __or__(self, other: 'RenderOpt | dict[str, Any]') -> Self:
        """Bitwise OR (``|``) implementation as shorthand for :meth:`replace`."""
        return self.replace(other)

    def changed(self) -> dict[str, Any]:
        """Returns a dictionary of this instance's attributes which are not set to their defaults."""
        return {k:v for k, v in self.model_dump(mode='python').items() if v != getattr(RENDER_OPT_DEFAULT, k)}

    def display(self, *, mark_changes: bool = True) -> str:
        """Returns these render option values in a string format for displaying.

        :param mark_changes: If ``True``, adds an asterisk to the end of field names whose values are not default.
        """
        changed: dict[str, Any] = self.changed()

        lines: list[str] = ['Render options:']
        for name, fld in self.model_dump(mode='python').items():
            lines.append(f'    {name}{'*' if mark_changes and (name in changed) else ''} = {fld!r}')

        return '\n'.join(lines)

    def replace(self, new: 'RenderOpt | dict[str, Any]') -> Self:
        """Returns a new ``RenderOpt`` based on this instance, with its values replaced by the contents of ``new``.

        If ``new`` is another ``RenderOpt``, it is turned into a dictionary of its non-default values via
        :meth:`changed`. Keys not defined in ``RenderOpt`` are ignored.
        """
        return self.__class__(**self.model_dump(mode='python') | (new.changed() if isinstance(new, RenderOpt) else new))

RENDER_OPT_DEFAULT = RenderOpt()
