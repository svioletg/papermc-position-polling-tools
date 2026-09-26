"""Logging functions."""
from pathlib import Path

from loguru import logger
from loguru._file_sink import FileDateFormatter
from rich.markup import escape

from positionpolling.const import (
    DEFAULT_LOGS_DIR,
    LOG_FILE_FORMAT,
    LOG_FILE_FORMAT_UTC,
    LOG_FILE_REGEX,
    LOG_MSG_FORMAT,
    LOG_MSG_FORMAT_STDOUT,
    LOG_MSG_FORMAT_STDOUT_UTC,
    LOG_MSG_FORMAT_UTC,
    NO_COLOR,
    console,
)


def clear_old_logs(keep: int, logs_dir: str | Path = DEFAULT_LOGS_DIR) -> None:
    """Deletes all but the ``keep`` most recent log files in the given directory matching :data:`LOG_FILE_REGEX`."""
    for n, fp in enumerate(sorted(
            (fp for fp in Path(logs_dir).glob('*.log') if LOG_FILE_REGEX.match(fp.name)),
            key=lambda fp: fp.stat().st_ctime_ns,
            reverse=True,
        )):
        if n > keep:
            fp.unlink()

def setup_logger(
        stdout_level: int | str = 'INFO',
        file_level: int | str = 'DEBUG',
        log_path: str | Path | None = None,
        *,
        utc: bool = True,
        no_color: bool | None = None,
        wrap_stdout: bool = False,
    ) -> tuple[int, tuple[int, Path] | None]:
    """Adds stdout and file handles for the project logger and returns the added handlers.

    If ``log_path`` is given a non-empty value, returns a tuple of the stdout handler ID and a tuple of the file handler
    ID with the log filepath being used. Otherwise if not logging to a file, a tuple of the stdout handler ID and
    ``None`` is returned.

    :param stdout_level: The maximum level of logs to show when logging to stdout.
    :param file_level: The maximum level of logs to show when logging to disk.
    :param log_path: Path to a file to start logging to, or to a directory. Any path without a file extension is assumed
        to be a directory. If a directory, the default log file name format (:data:`LOG_FILE_FORMAT_UTC` if
        ``utc=True``, otherwise :data:`LOG_FILE_FORMAT`) is used under that directory. If ``None``, no log file is
        created.

        .. note::
            If given a static path with no dynamic formatting, e.g. ``latest.log``, it will be **overwritten** by new
            logs created after this call.
    :param utc: Whether log timestamps are saved in UTC. If ``False``, the system's local timezone is used instead.
    :param no_color: Whether to disallow colored logs in terminal output. If ``None``, falls back on the value of
        :data:`NO_COLOR` set by the environment.
    :param wrap_stdout: Whether to wrap stdout log lines.
    """
    logger.remove()

    log_path = Path(log_path) if log_path else None

    # Set colors
    logger.level('TRACE', color='<dim><white>')
    logger.level('DEBUG', color='<cyan>')
    logger.level('INFO', color='<normal>')
    logger.level('WARNING', color='<yellow>')
    logger.level('ERROR', color='<light-red>')
    logger.level('CRITICAL', color='<bold><white><RED>')

    stdout_handle: int = logger.add(
        lambda s: console.print(escape(s), end='', soft_wrap=not wrap_stdout),
        level=stdout_level,
        format=LOG_MSG_FORMAT_STDOUT_UTC if utc else LOG_MSG_FORMAT_STDOUT,
        colorize=not (no_color if no_color is not None else NO_COLOR),
        diagnose=False,
    )

    log_file_format: str = LOG_FILE_FORMAT_UTC if utc else LOG_FILE_FORMAT

    file_handle: int = -1

    if log_path:
        if not log_path.suffix:
            log_path = log_path / log_file_format

        # Format manually so we can return the path
        log_path = log_path.with_name(log_path.name.format_map({'time': FileDateFormatter()}))

        file_handle = logger.add(
            log_path,
            level=file_level,
            format=LOG_MSG_FORMAT_UTC if utc else LOG_MSG_FORMAT,
            colorize=False,
            diagnose=True,
            retention=lambda _: clear_old_logs(10),
            delay=True,
            mode='w',
        )

    return stdout_handle, ((file_handle, log_path) if log_path else None)

def test_logs() -> None:
    """Sends a log message for every level."""
    logger.trace('TRACE')
    logger.debug('DEBUG')
    logger.info('INFO')
    logger.warning('WARNING')
    logger.error('ERROR')
    logger.critical('CRITICAL')
