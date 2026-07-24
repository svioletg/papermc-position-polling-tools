"""Constants, singletons, and common values or objects to be used by any module.

``const`` must not import from any other module in this project.
"""
import sys
from enum import IntEnum
from pathlib import Path

from loguru import logger

SCRIPT_ROOT: Path = Path(__file__).absolute().parent

DEFAULT_LOGS_DIR: Path = SCRIPT_ROOT / 'logs/'

LOG_MSG_FORMAT_UTC: str = '<level>[{time:YYYY-MM-DD HH:mm:ssZZ!UTC}] [{name}::{function}/{level}]: {message}</level>'
LOG_MSG_FORMAT: str = LOG_MSG_FORMAT_UTC.replace('!UTC', '')
LOG_FILE_FORMAT: str = '{time:YYYY-MM-DDTHHmmssZZ}.log'

logger.remove()

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
        sys.stdout,
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
            diagnose=True,
            retention=20,
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
