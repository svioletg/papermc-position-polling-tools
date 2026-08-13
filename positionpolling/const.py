"""Constants, singletons, and common values or objects to be used by any module.

``const`` must not import from any other module in this project.
"""
from enum import IntEnum, StrEnum
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.highlighter import Highlighter
from rich.markup import escape
from rich.text import Text
from rich.theme import Theme

logger.remove()

SCRIPT_ROOT: Path = Path(__file__).absolute().parent

DEFAULT_LOGS_DIR: Path = SCRIPT_ROOT / 'logs/'

LOG_MSG_FORMAT_UTC: str = '<level>[{time:YYYY-MM-DD HH:mm:ssZZ!UTC}] [{name}::{function}/{level}]: {message}</level>'
LOG_MSG_FORMAT: str = LOG_MSG_FORMAT_UTC.replace('!UTC', '')
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
        'info': 'cyan',
        'info2': 'bright_cyan',
        'ok': 'bright_green',
        'warn': 'yellow',
        'err': 'red',
        'dim': 'grey70',
        'path': 'magenta',
        'path2': 'bright_magenta',
        'cwd': 'grey50',
    })

    return Console(
        highlighter=ConsoleHighlighter(),
        theme=theme,
        emoji=False,
    )

console: Console = setup_rich_console()

class LogLevel(IntEnum):  # noqa: D101
    TRACE   = 5
    DEBUG   = 10
    INFO    = 20
    WARNING = 30
    ERROR   = 40

def setup_logger(
        stdout_level: int | str = 'INFO',
        file_level: int | str = 'DEBUG',
        logs_dir: str | Path | None = DEFAULT_LOGS_DIR,
        *,
        utc: bool = True,
    ) -> tuple[int, int | None]:
    """Adds stdout and file handles for the project logger and returns the stdout and file logger handles.

    :param stdout_level: The maximum level of logs to show when logging to stdout.
    :param file_level: The maximum level of logs to show when logging to disk.
    :param logs_dir: Where to store log files. If ``None``, nothing is logged to disk.
    :param utc: Whether log timestamps are saved in UTC. If ``False``, the system's local timezone is used instead.
    """
    logger.remove()

    # Set colors
    logger.level('TRACE', color='<dim><white>')
    logger.level('DEBUG', color='<cyan>')
    logger.level('INFO', color='<normal>')
    logger.level('WARNING', color='<yellow>')
    logger.level('ERROR', color='<red>')
    logger.level('CRITICAL', color='<bold><white><RED>')

    msg_format: str = LOG_MSG_FORMAT_UTC if utc else LOG_MSG_FORMAT

    stdout_handle: int = logger.add(
        lambda s: console.print(escape(s), end=''),
        level=stdout_level,
        format=msg_format,
        colorize=True,
        diagnose=True,
    )

    file_handle: int | None = None

    if logs_dir:
        file_handle = logger.add(
            Path(logs_dir, LOG_FILE_FORMAT),
            level=file_level,
            format=msg_format,
            colorize=False,
            diagnose=True,
            retention=10,
            delay=True,
            mode='w',
        )

    return stdout_handle, file_handle

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
