"""Miscellaneous common members used by various scripts."""
import shutil
import subprocess
import time
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, overload

from geometry import Grid2
from loguru import logger

if TYPE_CHECKING:
    from positionpolling.models import Entry


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

def convert_range(value: float, r_from: tuple[float, float], r_to: tuple[float, float]) -> float:
    """Returns a value relative to ``r_to`` as it is to ``r_from``.

    >>> assert convert_range(50, (0, 100), (-100, 100)) == 0
    """
    zero_dist_a, zero_dist_b = 0 - r_from[0], 0 - r_to[0]
    pct: float = (value + zero_dist_a) / (r_from[1] + zero_dist_a)

    return ((r_to[1] + zero_dist_b) * pct) - zero_dist_b

def expect[T](value: T | None, *exc_args: object) -> T:
    """Returns ``value`` if not ``None``, otherwise raises ``ValueError``."""
    if value is not None:
        return value

    raise ValueError(*exc_args or ('None',))

# Videos made with opencv seem to be unable to play in browsers or other applications unless reprocessed via ffmpeg
def fix_opencv_video(src: str | Path, dest: str | Path, *, same_file_ok: bool = False) -> None:
    """Runs a video created with ``cv2`` through FFmpeg to make it compatible with more players.

    :param same_file_ok: Whether ``src`` and ``dest`` are allowed to be the same path. If ``False``,
        ``shutil.SameFileError`` is raised, otherwise the source file is overwritten. Note that nothing is done to
        prevent overwriting ``dest`` if it exists but is not the same path as ``src``, check for this before calling the
        function if needed.
    """
    src = Path(src).absolute()
    dest = Path(dest).absolute()

    if src == dest:
        if not same_file_ok:
            raise shutil.SameFileError(f"'overwrite' is False and the destination path exists: {dest}")
        # Write to a temporary new file in case something goes wrong
        dest = src.with_suffix('.tmp' + src.suffix)

    assert_true(src.is_file(), f'Source path does not exist or is not a file: {src}')

    run(
        'ffmpeg', '-hide_banner', '-v', 'warning', '-y',
        '-i', str(src), '-vcodec', 'libx264', '-pix_fmt', 'yuv420p', str(dest),
        capture_output=False,
        raise_nonzero=True,
    )

    assert_true(dest.is_file(), f'Expected destination file at "{dest}"')

    if same_file_ok:
        shutil.move(dest, src)

# modified from:
# https://github.com/thearchcoder/Hueforge/blob/4942bcfcfeef26f8065bbebe672dec62dabe877e/hueforge/algorithms/other.py#L39-L50
def gradient(c1: tuple[int, int, int, int], c2: tuple[int, int, int, int], steps: int) \
    -> list[tuple[int, int, int, int]]:
    """Returns a list of colors (length ``steps``) that smoothly transition from ``c1`` to ``c2``.

    :raises ValueError:
        ``steps`` is not >=2.
    """
    if steps < 2:  # noqa: PLR2004
        raise ValueError(f"gradient() parameter 'steps' must be >=2: {steps!r}")

    return [blend_color(c1, c2, (n / (steps - 1)) * 100) for n in range(steps)]

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
        if val not in d:
            d[val] = [i]
        else:
            d[val].append(i)

    return d

def group_by_attr[T, U](it: Iterable[T], name: str, typ: type[U] | None = None, *, strict: bool = False) \
    -> dict[U, list[T]]:  # noqa: ARG001
    """Like :func:`group_by`, but works on an iterable of any object and groups by attribute values.

    Useful for things like dataclasses or models.

    :param typ: Can be used to cast the key type of the resulting dictionary, not used otherwise and
    :param strict: If ``False``, when one of the items in ``it`` does not have an attribute ``name``, it will be
        skipped. Otherwise, ``AttributeError`` is raised.
    """
    d: dict[U, list[T]] = {}

    for i in it:
        if (not strict) and (not hasattr(i, name)):
            continue
        val = getattr(i, name)
        if val not in d:
            d[val] = [i]
        else:
            d[val].append(i)

    return d

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
