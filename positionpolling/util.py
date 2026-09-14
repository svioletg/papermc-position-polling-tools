"""Miscellaneous common members used by various scripts."""
import colorsys
import re
import shutil
import subprocess
import time
from ast import literal_eval
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, TypeGuard, cast, overload

import webcolors
from geometry import Grid2
from loguru import logger
from maybetype import Err, Ok, Result

from positionpolling.const import UUID4_REGEX

if TYPE_CHECKING:
    from positionpolling.models import Entry

type ColorSource = Color | str | int | tuple[int, int, int] | tuple[int, int, int, int]
"""Type alias for valid :class:`Color` constructor inputs."""

class Color:
    """Class representing a color which can be constructed from and converted back out to various formats."""

    HSL_HSV_REGEX: ClassVar[re.Pattern[str]] = re.compile(r'^(hsl|hsv)\(.*\)$')
    """Matches an ``hsl(...)`` or ``hsv(...)`` string, capturing ``'hsl'`` or ``'hsv'``."""

    _value: int

    def __init__(self, source: ColorSource) -> None:
        """Construct a color from one of various formats.

        .. note::
            If ``source`` is given an integer, it will be treated as an RGBA value. This means that passing the
            hexadecimal form of an integer like ``0xffffff`` will not result in the RGB values ``255, 255, 255``, but
            ``0, 255, 255``, with an alpha value of ``255``. Make sure to include the last alpha byte if passing
            integers in this way.

        :param source: Either a string, a positive 32-bit integer, an RGB tuple (values 0-255), an RGBA tuple, or
            another :class:`Color` instance. If only RGB values are given (an RGB tuple, or a 24-bit hexadecimal value),
            the alpha value defaults to 255. If given a string, it can be either a hexadecimal color starting with ``#``
            or ``0x``, a CSS3 color keyword (see https://www.w3.org/TR/css-color-3/#colorunits), or a CSS-style
            ``hsl(...)`` or ``hsv(...)`` string.

            Since all named colors have an alpha value of 255, you can optionally suffix the name with ``#XX`` where
            ``XX`` is the hexadecimal alpha value to set for this color, e.g. ``'darkorchid#7f'``.

        :raises ValueError:
            - ``source`` is a tuple with less than 3 or greater than 4 items
            - ``source`` is a name string with more than two characters provided to an alpha specifier
            - ``source`` is a hexadecimal string whose value is neither 24-bit nor 32-bit

        .. include
        """
        if isinstance(source, Color):
            source = source.value

        if isinstance(source, str):
            source = self._parse_from_str(source)

        if isinstance(source, tuple):
            source = self._parse_from_tuple(source)

        self.value = source

    @property
    def value(self) -> int:
        """Integer value of this color.

        Trying to set this property to a non-``int`` will raise ``TypeError``. Setting it to a negative value or value
        greater than the 32-bit maximum will raise ``ValueError``.
        """
        return self._value

    @value.setter
    def value(self, new: int) -> None:
        if not isinstance(new, int):
            raise TypeError(f'Color value must be an integer: {new!r}')
        if new < 0:
            raise ValueError(f'Color value cannot be negative: {new!r}')
        if new > 0xffffffff:  # noqa: PLR2004
            raise ValueError(f'Color value cannot be larger than {0xffffffff}: {new!r}')

        self._value = new

    @property
    def r(self) -> int:
        """Red value."""
        return self._value >> 24

    @property
    def g(self) -> int:
        """Green value."""
        return (self._value >> 16) & 0xff

    @property
    def b(self) -> int:
        """Blue value."""
        return (self._value >> 8) & 0xff

    @property
    def a(self) -> int:
        """Alpha value."""
        return self._value & 0xff

    def __repr__(self) -> str:  # noqa: D105
        return f'{self.__class__.__name__}(value={self._value!r})'

    def __copy__(self) -> Self:
        """Returns a new instance with the same color value.

        .. include
        """
        return self.__class__(self._value)

    def __eq__(self, other: object) -> bool:
        """Compares the :data:`value` of this color with an integer, float, or another color instance's value.

        Comparing against any other type returns ``False``.

        .. include
        """
        if isinstance(other, self.__class__):
            return self._value == other._value
        if isinstance(other, int | float):
            return self._value == other

        return False

    def __hash__(self) -> int:
        """Returns the hash of the color's :data:`value`.

        .. include
        """
        return hash(self._value)

    def __iter__(self) -> Generator[int]:
        """Iterates over the RGBA values of this color.

        .. include
        """
        yield from (self.r, self.g, self.b, self.a)

    def __getitem__(self, idx: int) -> int:
        """Returns the channel value at the corresponding RGBA index.

        Does not allow negative indexing.

        :raises: ValueError
            ``idx`` is less than 0 or greater than 3.

        .. include
        """
        if not (0 <= idx <= 3):  # noqa: PLR2004
            raise ValueError(f'{self.__class__.__name__}.__getitem__() index must be between 0 and 3: {idx!r}')

        return (self._value >> (8 * (3 - idx))) & 0xff

    @staticmethod
    def _ensure_8bit(n: int) -> int:
        """Raises ``ValueError`` if ``n`` is not in the range 0-255, otherwise returns the value."""
        if not (0 <= n <= 255):  # noqa: PLR2004
            raise ValueError(f'Not in range 0-255: {n!r}')

        return n

    @staticmethod
    def _parse_from_str(source: str) -> int | tuple[int, int, int, int]:
        if isinstance(source, str) and Color.HSL_HSV_REGEX.match(source):
            return Color._parse_hsl_hsv(source)

        if (source[0] != '#') and (not source.startswith('0x')):
            # Check if alpha was specified
            name, *extra = source.split('#', maxsplit=1)
            extra = extra[0] if extra else ''
            if len(extra) > 2:  # noqa: PLR2004
                raise ValueError(f'Expected a maximum of two characters for hexadecimal alpha value: {source!r}')
            extra = extra or 'ff'
            source = webcolors.name_to_hex(name) + extra.rjust(2, '0')

        source = source.replace('#', '0x')

        if len(source) == 8:  # noqa: PLR2004
            source += 'ff'
        if len(source) != 10:  # noqa: PLR2004
            raise ValueError(f'Expected 6 or 8 hexadecimal characters for color value: {source!r}')

        return int(literal_eval(source.replace('#', '0x')))

    @staticmethod
    def _parse_from_tuple(source: tuple[int, int, int] | tuple[int, int, int, int]) -> int:
        if len(source) not in (3, 4):
            raise ValueError(f'Color tuple must be either 3 or 4 values: {source!r}')
        if len(source) == 3:  # noqa: PLR2004
            source = (*source, 255)

        # Lazy way to do this but it works
        return int(literal_eval(f'0x{source[0]:02x}{source[1]:02x}{source[2]:02x}{source[3]:02x}'))

    @staticmethod
    def _parse_hsl_hsv(string: str) -> tuple[int, int, int, int]:
        """Parses an ``hsl(...)`` or ``hsv(...)`` string to RGBA values.

        3 or 4 number values must be given, where the 4th is used as the alpha value. If a 4th value is not given, the
        alpha value defaults to 1 (255). The converted values are rounded according to the built-in :func:`round`.
        """
        if not (m := Color.HSL_HSV_REGEX.match(string)):
            raise ValueError(f'Expected HSL/HSV string to be in format "hsl(...)" or "hsv(...)": {string!r}')
        mode = cast('Literal["hsl", "hsv"]', m.groups(0)[0])

        ns: list[float] = [float(m) for m in re.findall(r'(\d+(?:\.\d+)?)', string)]
        if len(ns) not in (3, 4):
            raise ValueError(f'Expected 3 or 4 number values for HSV/HSL string: {string!r}')

        h, s, vl, a, *_ = [*ns, 1] # Default alpha to 1
        if not (0 <= h <= 360):  # noqa: PLR2004
            raise ValueError(f'Hue value not in range 0-360: {h!r}')
        if not (0 <= s <= 100):  # noqa: PLR2004
            raise ValueError(f'Saturation value not in range 0-100: {s!r}')
        if not (0 <= vl <= 100):  # noqa: PLR2004
            raise ValueError(f'{'Lightness' if mode == 'hsl' else 'Brightness'} value not in range 0-100: {vl!r}')
        if not (0 <= a <= 1):
            raise ValueError(f'Alpha value not in range 0-1: {a!r}')

        match mode:
            case 'hsl':
                r, g, b = colorsys.hls_to_rgb(
                    convert_range(h, (0, 360), (0, 1)),
                    convert_range(vl, (0, 100), (0, 1)),
                    convert_range(s, (0, 100), (0, 1)),
                )
            case 'hsv':
                r, g, b = colorsys.hsv_to_rgb(
                    convert_range(h, (0, 360), (0, 1)),
                    convert_range(s, (0, 100), (0, 1)),
                    convert_range(vl, (0, 100), (0, 1)),
                )
            case _:
                raise ValueError(f'Unexpected mode: {mode!r}')

        return (round(r * 255), round(g * 255), round(b * 255), round(convert_range(a, (0, 1), (0, 255))))

    # Output

    def hex(self, prefix: str = '0x', *, alpha: bool = True) -> str:
        """Returns the hexadecimal string for this color with a specified prefix.

        :param alpha: Discards the alpha value if ``False``.
        """
        s: str = f'{prefix}{self._value:08x}'

        return s if alpha else s[:-2]

    def hsl(self, *, css: bool = False) -> tuple[float, float, float]:
        """Returns this color in HSL format.

        Each value is a float ranging from 0 to 1 by default, passing ``css=True`` will return them in ranges 0-360,
        0-100, and 0-100 respectively.
        """
        h, l, s = colorsys.rgb_to_hls(self.r / 255, self.g / 255, self.b / 255)  # noqa: E741

        return (
            convert_range(h, (0, 1), (0, 360)) if css else h,
            convert_range(s, (0, 1), (0, 100)) if css else s,
            convert_range(l, (0, 1), (0, 100)) if css else l,
        )

    def hsla(self, *, css: bool = False) -> tuple[float, float, float, float]:
        """Returns this color in HSLA format.

        Each value is a float ranging from 0 to 1 by default, passing ``css=True`` will return them in ranges 0-360,
        0-100, 0-100, and 0-1 respectively.
        """
        return (*self.hsl(css=css), self.a / 255)

    def hsv(self, *, css: bool = False) -> tuple[float, float, float]:
        """Returns this color in HSL format.

        Each value is a float ranging from 0 to 1 by default, passing ``css=True`` will return them in ranges 0-360,
        0-100, and 0-100 respectively.
        """
        h, s, v = colorsys.rgb_to_hsv(self.r / 255, self.g / 255, self.b / 255)

        return (
            convert_range(h, (0, 1), (0, 360)) if css else h,
            convert_range(s, (0, 1), (0, 100)) if css else s,
            convert_range(v, (0, 1), (0, 100)) if css else v,
        )

    def hsva(self, *, css: bool = False) -> tuple[float, float, float, float]:
        """Returns this color in HSVA format.

        Each value is a float ranging from 0 to 1 by default, passing ``css=True`` will return them in ranges 0-360,
        0-100, 0-100, and 0-1 respectively.
        """
        return (*self.hsl(css=css), self.a / 255)

    def rgb(self) -> tuple[int, int, int]:
        """Returns the RGB tuple for this color."""
        return (self.r, self.g, self.b)

    def rgba(self) -> tuple[int, int, int, int]:
        """Returns the RGBA tuple for this color."""
        return (self.r, self.g, self.b, self.a)

    def name(self) -> str | None:
        """Returns the CSS3 name, if any, for this color.

        Alpha value is ignored. Returns ``None`` if a name was not found.
        """
        try:
            return webcolors.hex_to_name(self.hex('#', alpha=False))
        except ValueError:
            return None

    # Transformations

    def blend(self, other: Self | ColorSource, delta: float = 50.0) -> Self:
        """Returns a new color with this instance's value blended with another's."""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)

        return self.__class__(blend_color(self.rgba(), other.rgba(), delta))

    def gradient(self, other: Self | ColorSource, steps: int) -> Generator[Self]:
        """Yields colors (length ``steps``) that smoothly transition from ``self`` to ``other``."""
        if not isinstance(other, self.__class__):
            other = self.__class__(other)

        yield from (self.__class__(step) for step in gradient(self.rgba(), other.rgba(), steps))

    def replace(self,
            *,
            r: int | None = None,
            g: int | None = None,
            b: int | None = None,
            a: int | None = None,
        ) -> Self:
        """Returns a new color with any of its RGBA values replaced."""
        r = self._ensure_8bit(r) if r is not None else self.r
        g = self._ensure_8bit(g) if g is not None else self.g
        b = self._ensure_8bit(b) if b is not None else self.b
        a = self._ensure_8bit(a) if a is not None else self.a

        return self.__class__((r, g, b, a))

def ask(prompt: str, choices: Sequence[str], *, strict_case: bool = False) -> str:
    """Shows an input prompt and keeps asking until the response is in ``choices``, returning the choice.

    :param strict_case: If ``False``, all choices and the user's response are converted to lowercase.
    """
    if not strict_case:
        choices = [s.lower() for s in choices]

    while True:
        choice = input(prompt).strip()
        if (choice if strict_case else (choice := choice.lower())) in choices:
            return choice

def ask_overwrite(path: Path) -> bool:
    """Checks whether ``path`` exists and, if it does, shows a y/n prompt to overwrite it.

    Returns ``True`` for a response ``'y'``, ``False`` otherwise. If ``path`` does not exist, returns ``True`` and skips
    the prompt.
    """
    return True if not path.exists() else \
        ask(f'Destination file "{path}" already exists. Overwrite? (y/n) ', 'yn') == 'y'

def assert_all(
        values: Iterable[object],
        predicate: Callable[[object], bool] = bool,
        msg: str = 'predicate ({i!r}) is False',
    ) -> None:
    """Raises ``AssertionError`` if ``predicate(i)`` is ``True`` for any ``i`` in ``values``.

    :param msg: A string to use for the raised ``AssertionError``, being formatted with ``i``.
    """
    for i in values:
        if not predicate(i):
            raise AssertionError(msg.format(i=i))

def assert_true(condition: object, *exc_args: object) -> None:
    """Raises ``AssertionError`` if ``not condition``, otherwise does nothing."""
    if not condition:
        raise AssertionError(*exc_args)

# modified from:
# https://github.com/thearchcoder/Hueforge/blob/4942bcfcfeef26f8065bbebe672dec62dabe877e/hueforge/algorithms/other.py#L4-L19
def blend_color(c1: tuple[int, int, int, int], c2: tuple[int, int, int, int], delta: float = 50.0) \
    -> tuple[int, int, int, int]:
    """Returns a color blended some percentage of the way toward ``c2``, determined by ``delta``."""
    delta = max(0.0, min(delta, 100.0))
    factor = delta / 100.0

    r1, g1, b1, a1 = c1
    r2, g2, b2, a2 = c2

    return (
        int(r1 * (1 - factor) + r2 * factor),
        int(g1 * (1 - factor) + g2 * factor),
        int(b1 * (1 - factor) + b2 * factor),
        int(a1 * (1 - factor) + a2 * factor),
    )

def coerce[T](obj: object, typ: type[T], fn: Callable[[object], T] | None = None) -> T:
    """Returns ``obj`` if it is already of type ``typ``, otherwise converts it to that type.

    ``fn`` can be used to specify an alternate function to convert the value with; if ``None``, this defaults to the
    type constructor.
    """
    return obj if isinstance(obj, typ) else (fn or typ)(obj)  # ty: ignore[too-many-positional-arguments]

@overload
def comma_split[T](s: str, fn: Callable[[list[str]], T], *, strip: bool = False) -> T: ...
@overload
def comma_split[T](s: str, fn: None = None, *, strip: bool = False) -> list[str]: ...
def comma_split[T](s: str, fn: Callable[[list[str]], T] | None = None, *, strip: bool = False) -> T | list[str]:
    """Splits a string by commas and returns ``typ`` called with the split list.

    If ``typ`` is ``None``, the list is returned. Strips whitespace if ``strip=True``.
    """
    split: list[str] = s.split(',') if not strip else [i.strip() for i in s.split(',')]

    return split if not fn else fn(split)

def convert_range(value: float, r_from: tuple[float, float], r_to: tuple[float, float]) -> float:
    """Returns a value relative to ``r_to`` as it is to ``r_from``.

    If both values of ``r_from`` are equal, the first value of ``r_to`` is returned.

    >>> assert convert_range(50, (0, 100), (-100, 100)) == 0
    """
    zero_dist_a, zero_dist_b = 0 - r_from[0], 0 - r_to[0]
    # Default denominator to 1 if 0 to avoid dividing by 0
    pct: float = (value + zero_dist_a) / ((r_from[1] + zero_dist_a) or 1)

    return ((r_to[1] + zero_dist_b) * pct) - zero_dist_b

def dict_entries[K, V](d: Mapping[K, V], labels: tuple[str, str] = ('key', 'value')) -> list[dict[str, K | V]]:
    """Transforms a key-value dictionary into a list of dictionaries with the keys and values as separate fields.

    >>> d = {'a': 1, 'b': 2, 'c': 3}
    >>> assert dict_entries(d) == [
    ...     {'key': 'a', 'value': 1},
    ...     {'key': 'b', 'value': 2},
    ...     {'key': 'c', 'value': 3},
    ... ]
    >>> assert dict_entries(d, ('letter', 'number')) == [
    ...     {'letter': 'a', 'number': 1},
    ...     {'letter': 'b', 'number': 2},
    ...     {'letter': 'c', 'number': 3},
    ... ]
    """
    key, value = labels

    return [{key:k, value:v} for k, v in d.items()]

def drop_duplicates[T](it: Iterable[T], compare: Callable[[T, T], bool] | None = None) -> list[T]:
    """Returns a list of only the unique items of ``it``.

    While slower than ``set(it)``, this function ensures that the original order is preserved, where the order of
    resulting ``set`` items is not guaranteed.

    :param key: Function used to compare the equality of two items and determine whether it should be added to the list
        of unique items. Note that this will result in a much slower operation (potentially ``O(n * n)``); when
        ``None``, a ``set`` is used to keep track of unique items and each item is simply checked to not be in that set,
        which is an ``O(1)`` operation for each item.
    """
    unique: list[T] = []

    if compare:
        for i in it:
            if any(compare(i, j) for j in unique):
                continue
            unique.append(i)
    else:
        counted: set[T] = set()
        for i in it:
            if i not in counted:
                unique.append(i)
                counted.add(i)

    return unique

def expect[T](value: T | None, *exc_args: object) -> T:
    """Returns ``value`` if not ``None``, otherwise raises ``ValueError``."""
    if value is not None:
        return value

    raise ValueError(*exc_args or ('None',))

# Videos made with opencv seem to be unable to play in browsers or other applications unless reprocessed via ffmpeg
def fix_opencv_video(src: str | Path, dest: str | Path, *, same_file_ok: bool = False) \
    -> Result[Path, subprocess.CompletedProcess]:
    """Runs a video created with ``cv2`` through FFmpeg to make it compatible with more players.

    .. important::
        |requires-ffmpeg|

    :param same_file_ok: Whether ``src`` and ``dest`` are allowed to be the same path. If ``False``,
        ``shutil.SameFileError`` is raised, otherwise the source file is overwritten. Note that nothing is done to
        prevent overwriting ``dest`` if it exists but is not the same path as ``src``, check for this before calling the
        function if needed.
    """
    ffmpeg: str = require_ffmpeg()

    src = Path(src).absolute()
    dest = Path(dest).absolute()

    if src == dest:
        if not same_file_ok:
            raise shutil.SameFileError(f"'overwrite' is False and the destination path exists: {dest}")
        # Write to a temporary new file in case something goes wrong
        dest = src.with_suffix('.tmp' + src.suffix)

    assert_true(src.is_file(), f'Source path does not exist or is not a file: {src}')

    proc = run(
        ffmpeg, '-hide_banner', '-v', 'warning', '-y',
        '-i', str(src), '-vcodec', 'libx264', '-pix_fmt', 'yuv420p', str(dest),
        capture_output=False,
        raise_nonzero=False,
    )

    if proc.returncode != 0:
        return Err(proc)

    assert_true(dest.is_file(), f'Expected destination file at "{dest}"')

    if same_file_ok:
        shutil.move(dest, src)
        # So that we return the right destination path if we're overwriting
        dest = src

    return Ok(dest)

def flatten(it: Iterable, *, iter_str: bool = False) -> list:
    """Flattens a multi-dimensional iterable into a flat list.

    :param iter_str: Whether to count strings as iterable, and thus flatten them into the list as well. If ``it`` is a
        string, a list containing just that string is returned.
    """
    flat: list = []

    def can_flatten(obj: object) -> TypeGuard[Iterable]:
        if isinstance(obj, Iterable):
            if iter_str:
                return True
            return not isinstance(obj, str)
        return False

    def _flatten(obj: object):  # noqa: ANN202
        if can_flatten(obj):
            if isinstance(obj, str) and (len(obj) == 1):
                # Check this to avoid an infinite loop with one-character strings
                flat.append(obj)
            else:
                for i in obj:
                    if can_flatten(obj):
                        _flatten(i)
                    else:
                        flat.append(i)
        else:
            flat.append(obj)

    _flatten(it)

    return flat

# modified from:
# https://github.com/thearchcoder/Hueforge/blob/4942bcfcfeef26f8065bbebe672dec62dabe877e/hueforge/algorithms/other.py#L39-L50
def gradient(c1: tuple[int, int, int, int], c2: tuple[int, int, int, int], steps: int) \
    -> Generator[tuple[int, int, int, int]]:
    """Yields colors (length ``steps``) that smoothly transition from ``c1`` to ``c2``.

    A ``steps`` value of 1 yields ``c2`` immediately, a value of 0 or less yields nothing.
    """
    if steps == 1:
        yield c2
    else:
        yield from (blend_color(c1, c2, (n / (steps - 1)) * 100) for n in range(steps))

def grid_from_entries(data: Iterable['Entry'], **grid_kwargs: Any) -> Grid2:  # noqa: ANN401
    """Returns a grid created from the minimum and maximum ``x`` and ``z`` values of ``data``'s entries."""
    return Grid2(
        min(e.x for e in data),
        min(e.z for e in data),
        max(e.x for e in data),
        max(e.z for e in data),
        **grid_kwargs,
    )

def group_by[K, V](it: Iterable[Mapping[K, V]], key: K, *, strict: bool = False) -> dict[V, list[Mapping[K, V]]]:
    """Groups mappings together into a new dictionary by the value of a given key.

    Example:

    .. code-block:: python

        items = [
            {'title': 'Talking Book', 'artist': 'Stevie Wonder'},
            {'title': 'Heroes', 'artist': 'David Bowie'},
            {'title': 'Innervisions', 'artist': 'Stevie Wonder'},
        ]

        by_artist = group_by(items, 'artist')
        assert by_artist == {
            'Stevie Wonder': [
                {'title': 'Talking Book', 'artist': 'Stevie Wonder'},
                {'title': 'Innervisions', 'artist': 'Stevie Wonder'},
            ],
            'David Bowie': [
                {'title': 'Heroes', 'artist': 'David Bowie'},
            ]
        }

    :param strict: If ``False``, when ``key`` is not found in one of ``it`` 's mappings, the item is skipped. Otherwise,
        ``KeyError`` is raised.
    """
    d: dict[V, list[Mapping[K, V]]] = {}

    for i in it:
        if (not strict) and (key not in i):
            continue
        val = i[key]
        d.setdefault(val, []).append(i)

    return d

def group_by_attr[T, U](it: Iterable[T], name: str, typ: type[U] | None = None, *, strict: bool = False) \
    -> dict[U, list[T]]:  # noqa: ARG001
    """Like :func:`group_by`, but works on an iterable of any object and groups by attribute values.

    Useful for things like dataclasses or models.

    :param typ: Can be used to cast the key type of the resulting dictionary; not used at runtime.
    :param strict: If ``False``, when one of the items in ``it`` does not have an attribute ``name``, it will be
        skipped. Otherwise, ``AttributeError`` is raised.
    """
    d: dict[U, list[T]] = {}

    for i in it:
        if (not strict) and (not hasattr(i, name)):
            continue
        val = getattr(i, name)
        d.setdefault(val, []).append(i)

    return d

def log_progress(
        completed: float,
        total: float,
        description: str = 'Progress: ',
        *,
        pct_digits: int = 1,
        show_count: bool = True,
        level: int | str = 'INFO',
    ) -> None:
    """Writes a log in the format ``'{description}p% (m/n) complete'`` using the values given.

    The ``completed`` value will be aligned to the right according to the width of ``total``, the percentage is aligned
    to the right so as to fit ``100%`` plus any number of precision digits used.

    Will be logged with a ``depth`` of 1, meaning the function given to the log record will be the caller of this
    function and won't show as ``log_progress``.

    :param description: Text to add before the progress values.
    :param pct_digits: How many digits of precision to format the percentage with. Must be >=0. 0 rounds to the nearest
        integer. 1 = ``100.0%``, 2 = ``100.00%``, etc.
    :param show_count: If ``False``, the ``(m/n)`` portion of the message is omitted, leaving only the percentage.

    :raises ValueError:
        ``pct_digits`` is less than 0.
    """
    if pct_digits < 0:
        raise ValueError(f'pct_digits value must be positive: {pct_digits!r}')

    total_width: int = len(str(total))
    pct_width: int = 4 if pct_digits == 0 else 5 + pct_digits
    progress: float = completed / total
    logger.opt(depth=1).log(
        level,
        f'{description}{progress:>{pct_width}.{pct_digits}%}'
        + (f' ({completed:>{total_width}}/{total})' if show_count else '')
        + ' complete',
    )

def parse_players(
        players: Sequence[str],
        player_map: Mapping[str, str],
        missing: Callable[[str], Any] | Literal['pass'] | None = None,
    ) -> list[str]:
    """Returns a list of player UUIDs using ``player_map`` to look up non-UUIDs in ``players``.

    Values of ``players`` that are valid UUIDs (matching :data:`const.UUID4_REGEX`) are added to the returned list
    as-is, otherwise they are used as a key for ``player_map`` and the resulting value is used.

    :param missing: How to handle a value in ``players`` which is not a UUID and does not exist in ``player_map``. If
        ``None`` (default), :class:`KeyError` is raised. ``'pass'`` skips the value silently. If given a callable, it
        is called with the key in question as the sole argument.
    """
    parsed_players: list[str] = []

    for player in players:
        try:
            parsed_players.append(player if UUID4_REGEX.match(player) else str(player_map[player]))
        except KeyError:
            if missing is None:
                raise

            if missing == 'pass':
                pass
            elif callable(missing):
                missing(player)
            else:
                raise ValueError(f"'missing' parameter not None, 'pass', or a callable object: {missing!r}")  # noqa: B904

    return parsed_players

def require_ffmpeg() -> str:
    """Returns the binary path for FFmpeg or raises :class:`FileNotFoundError` if it could not be found."""
    if not (ffmpeg := shutil.which('ffmpeg')):
        raise FileNotFoundError('ffmpeg could not be found and is required for this operation')

    return ffmpeg

def rgba(hexcolor: str) -> tuple[int, int, int, int]:
    """Converts a hexadecimal color string to an RGBA tuple.

    Accepted formats are (all with or without a leading ``#``):
      - ``ff0000ff`` (full RGBA hex code, returns ``(255, 0, 0, 255)``)
      - ``ff0000`` (if not given, alpha value defaults to 255: ``(255, 0, 0, 255)``)
      - ``0af`` (expands to ``00aaff``, and thus ``(0, 170, 255, 170)``)
      - ``0afa`` (expands to ``00aaffaa``, and thus ``(0, 170, 255, 170)``)
    """
    hexcolor = hexcolor.lstrip('#')
    match len(hexcolor):
        case 3 | 4:
            hexcolor = ''.join(i+i for i in hexcolor)

    match len(hexcolor):
        case 6:
            return (int(hexcolor[0:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:6], 16), 255)
        case 8:
            return (int(hexcolor[0:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:6], 16), int(hexcolor[6:8], 16))

    raise ValueError(f'Could not parse color: {hexcolor!r}')

def run(
        *args: str,
        capture_output: bool = True,
        on_fail: Callable[[subprocess.CompletedProcess], None] | Literal['dump'] | None = None,
        raise_nonzero: bool = False,
    ) -> subprocess.CompletedProcess:
    """Runs a command, optionally capturing its output.

    :param capture_output: Whether to capture the process' output, redirecting it from each respective stream to the
        stream attributes of the returned ``subprocess.CompletedProcess`` instance.
    :param on_nonzero: What action to take when the process exits with a non-zero exit code. Can be a callable which
        takes process (``subprocess.CompletedProcess``) as its sole argument, the string ``'dump'``, or ``None``.
        If ``dump``, the captured ``stderr`` output (if applicable) is logged. If ``None``, no action is taken.
    :param raise_nonzero: Whether to raise ``subprocess.CalledProcessError`` if the process returned a non-zero exit
        code, raised after the action for ``on_fail`` is done.
    """
    logger.info(f'Run: {args}')
    proc = subprocess.run(args, capture_output=capture_output, check=False)  # noqa: S603

    if proc.returncode != 0:
        if callable(on_fail):
            on_fail(proc)
        elif on_fail == 'dump':
            logger.error(f'----- ffmpeg exited with non-zero status {proc.returncode}; stderr below -----')
            logger.error('\n' + proc.stderr.decode('utf-8'))
            logger.error('----- end of captured output -----')

        if raise_nonzero:
            raise subprocess.CalledProcessError(proc.returncode, args)

    return proc

@contextmanager
def time_this(dest: list[float]) -> Generator[None]:
    """Context manager which stores the time taken to execute the code in its block to ``dest``."""
    ta: float = time.perf_counter()
    try:
        yield
    finally:
        dest.append(time.perf_counter() - ta)

@overload
def try_next[T, U](it: Iterator[T], default: U) -> T | U: ...
@overload
def try_next[T, U](it: Iterator[T], default: T | None = None) -> T | None: ...
def try_next[T, U](it: Iterator[T], default: U | None = None) -> T | U | None:
    """Tries to call ``next()`` on an iterator, returning ``default`` if ``StopIteration`` was raised."""
    try:
        return next(it)
    except StopIteration:
        return default
