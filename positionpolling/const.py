"""Constants, singletons, and common values or objects to be used by any module.

``const`` must not import from any other module in this project.
"""
import os
import re
import warnings
from collections.abc import Mapping
from enum import IntEnum
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.highlighter import Highlighter
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
LOG_FILE_REGEX: re.Pattern[str] = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{6}\+\d{4}\.log$')

Y_RANGE: dict[str, tuple[int, int]] = {
    'minecraft:overworld': (-64, 320),
    'minecraft:the_nether': (0, 127),
    'minecraft:the_end': (0, 255),
}

Y_HUE_RANGE = (0, 300)

VANILLA_WORLDS: list[str] = ['minecraft:overworld', 'minecraft:the_nether', 'minecraft:the_end']

UUID4_REGEX: re.Pattern[str] = re.compile(r'[a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12}')
"""Matches the UUID4 format with or without separating hyphens."""

class ConsoleHighlighter(Highlighter):
    """Custom highlighter class for the ``rich`` console."""

    def highlight(self, text: Text) -> None:  # noqa: D102
        pass

class LogLevel(IntEnum):  # noqa: D101
    TRACE    = 5
    DEBUG    = 10
    INFO     = 20
    WARNING  = 30
    ERROR    = 40
    CRITICAL = 50

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
