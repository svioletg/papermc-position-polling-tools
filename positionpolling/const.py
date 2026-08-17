"""Constants, singletons, and common values or objects to be used by any module.

``const`` must not import from any other module in this project.
"""
import os
import warnings
from collections.abc import Mapping
from enum import IntEnum, StrEnum
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.highlighter import Highlighter
from rich.markup import escape
from rich.text import Text
from rich.theme import Theme

from positionpolling.errors import ValueWarning

logger.remove()

def get_env_bool(key: str, *, strict: bool = False, env: Mapping[str, str] | None = None) -> bool:
    """Returns a boolean value for an environment variable.

    Returns ``True`` if the value is 1 or "true" (case-insensitive), returns ``False`` if 0 or "false".

    :param strict: If ``True``, ``ValueError`` is raised when the value of this variable is not an accepted boolean
        value. If ``False``, ``False`` is returned in this case along with emitting a :class:`errors.ValueWarning`.
    """
    env = env if env is not None else os.environ

    if not (value := env.get(key)):
        return False

    if value.lower() in ['1', 'true']:
        return True

    if (value.lower() not in ['0', 'false']):
        if strict:
            raise ValueError(f'Boolean environment variable must be any of 1/true/0/false: {value!r}')
        warnings.warn(
            'Boolean environment variable expected to be any of 1/true/0/false; defaulting to false',
            ValueWarning,
            stacklevel=2,
        )

    return False

PACKAGE_ROOT: Path = Path(__file__).absolute().parent

ENV_PREFIX: str = 'MCPOSLOG'

NO_COLOR: bool = get_env_bool(f'{ENV_PREFIX}_NO_COLOR')
"""Whether color should be disallowed in terminal output."""

DEFAULT_LOGS_DIR: Path = PACKAGE_ROOT / 'logs/'

LOG_MSG_FORMAT_UTC: str = '<level>[{time:YYYY-MM-DD HH:mm:ssZZ!UTC}] [{name}::{function}/{level}]: {message}</level>'
LOG_MSG_FORMAT: str = LOG_MSG_FORMAT_UTC.replace('!UTC', '')
LOG_MSG_FORMAT_STDOUT_UTC: str = '<level>[{time:HH:mm:ss!UTC}] [{name}::{function}/{level}]: {message}</level>'
"""Log message format used for the stdout sink, which omits the full date but still includes the time."""
LOG_MSG_FORMAT_STDOUT: str = LOG_MSG_FORMAT_STDOUT_UTC.replace('!UTC', '')
"""The same as :data:`LOG_MSG_FORMAT_STDOUT_UTC`, but in local time."""
LOG_FILE_FORMAT_UTC: str = '{time:YYYY-MM-DDTHHmmssZZ!UTC}.log'
LOG_FILE_FORMAT: str = '{time:YYYY-MM-DDTHHmmssZZ}.log'

Y_RANGE: dict[str, tuple[int, int]] = {
    'minecraft:overworld': (-64, 320),
    'minecraft:the_nether': (0, 127),
    'minecraft:the_end': (0, 255),
}

Y_HUE_RANGE = (0, 300)

class ConsoleHighlighter(Highlighter):
    """Custom highlighter class for the ``rich`` console."""

    def highlight(self, text: Text) -> None:  # noqa: D102
        pass

def setup_rich_console() -> Console:
    """Prepares a ``rich`` console and returns it."""
    theme = Theme({
        'bar.complete': 'bright_blue',
        'bar.finished': 'green',
        'progress.description': 'cyan',
        'progress.elapsed': '',

        'info': 'cyan',
        'info2': 'bright_cyan',
        'ok': 'bright_green',
        'warn': 'yellow',
        'err': 'bright_red',
        'dim': 'grey70',
        'path': 'magenta',
        'path2': 'bright_magenta',
        'cwd': 'grey50',
    })

    return Console(
        highlighter=ConsoleHighlighter(),
        theme=theme,
        emoji=False,
        no_color=NO_COLOR,
    )

console: Console = setup_rich_console()

class LogLevel(IntEnum):  # noqa: D101
    TRACE    = 5
    DEBUG    = 10
    INFO     = 20
    WARNING  = 30
    ERROR    = 40
    CRITICAL = 50

def setup_logger(
        stdout_level: int | str = 'INFO',
        file_level: int | str = 'DEBUG',
        logs_dir: str | Path | None = DEFAULT_LOGS_DIR,
        *,
        utc: bool = True,
        no_color: bool | None = None,
    ) -> tuple[int, tuple[int, Path] | None]:
    """Adds stdout and file handles for the project logger and returns the added handlers.

    Returns a tuple of the stdout handler ID and a tuple of the file handler ID and the log directory being used, if
    file logging was enabled. If ``logs_dir`` is ``None``, the second tuple item is ``None`` instead.

    :param stdout_level: The maximum level of logs to show when logging to stdout.
    :param file_level: The maximum level of logs to show when logging to disk.
    :param logs_dir: Where to store log files. If ``None``, nothing is logged to disk.
    :param utc: Whether log timestamps are saved in UTC. If ``False``, the system's local timezone is used instead.
    :param no_color: Whether to disallow colored logs in terminal output. If ``None``, falls back on the value of
        :data:`NO_COLOR` set by the environment.
    """
    logger.remove()

    logs_dir = Path(logs_dir) if logs_dir else None

    # Set colors
    logger.level('TRACE', color='<dim><white>')
    logger.level('DEBUG', color='<cyan>')
    logger.level('INFO', color='<normal>')
    logger.level('WARNING', color='<yellow>')
    logger.level('ERROR', color='<light-red>')
    logger.level('CRITICAL', color='<bold><white><RED>')

    stdout_handle: int = logger.add(
        lambda s: console.print(escape(s), end=''),
        level=stdout_level,
        format=LOG_MSG_FORMAT_STDOUT_UTC if utc else LOG_MSG_FORMAT_STDOUT,
        colorize=not (no_color if no_color is not None else NO_COLOR),
        diagnose=True,
    )

    log_file_format: str = LOG_FILE_FORMAT_UTC if utc else LOG_FILE_FORMAT

    file_handle: int = -1

    if logs_dir:
        file_sink = Path(logs_dir, log_file_format)

        file_handle = logger.add(
            file_sink,
            level=file_level,
            format=LOG_MSG_FORMAT_UTC if utc else LOG_MSG_FORMAT,
            colorize=False,
            diagnose=True,
            retention=10,
            delay=True,
            mode='w',
        )

    return stdout_handle, ((file_handle, logs_dir) if logs_dir else None)

def test_logs() -> None:
    """Sends a log message for every level."""
    logger.trace('TRACE')
    logger.debug('DEBUG')
    logger.info('INFO')
    logger.warning('WARNING')
    logger.error('ERROR')
    logger.critical('CRITICAL')

class World(StrEnum):
    """A vanilla Minecraft world identifier."""

    OVERWORLD = 'minecraft:overworld'
    NETHER = 'minecraft:the_nether'
    END = 'minecraft:the_end'
