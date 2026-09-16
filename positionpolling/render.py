"""Common functionality used by most render modules."""
import time
from collections.abc import Iterable, Sequence
from datetime import timedelta
from pathlib import Path
from subprocess import CompletedProcess

import cv2
from loguru import logger
from maybetype import Err, Ok, Result
from rich.progress import Column, Progress, TaskProgressColumn, TextColumn

from positionpolling.const import console
from positionpolling.models import Entry, PlayerPositions
from positionpolling.rich import CustomBarColumn
from positionpolling.util import fix_opencv_video


def check_video_path(video_path: str | Path | None) -> Path | None:
    """Returns the absolute path for ``video_path`` if its parent directory exists, or ``None`` if ``None``.

    :raises: FileNotFoundError
        The parent directory of the video path does not exist.
    """
    if not video_path:
        return None

    video_path = Path(video_path).absolute()
    if video_path and not video_path.parent.exists():
        raise FileNotFoundError(f'Directory does not exist: {video_path.parent}')

    return video_path

def fix_video(video_path: str | Path) -> None:
    """Reprocess the video at ``video_path`` with FFmpeg to a more widely compatible format, logging any issues."""
    fix_result: Result[Path, CompletedProcess]
    try:
        fix_result = fix_opencv_video(video_path, video_path, same_file_ok=True)
    except FileNotFoundError as e:
        # Log warning and continue on if FFmpeg isn't installed instead of raising an error
        if 'ffmpeg could not be found' in str(e):
            logger.warning('FFmpeg is not installed, skipping fix_opencv_video step')
            return
        else:
            raise

    match fix_result:
        case Ok(dest):
            logger.info(f'Video reprocessed successfully and saved to {dest}')
        case Err(proc):
            logger.error(f'FFmpeg process failed with status {proc.returncode}')
            logger.info('Video reprocessing failed, the original video is unmodified')

def get_frame_estimate(
        entries: Sequence[Entry],
        *,
        time_factor: float,
        fps: int,
        log: bool = False,
    ) -> int:
    """Estimate how many frames long a render of these entries should be based on the given time factor and fps."""
    total_entry_duration = timedelta(seconds=entries[-1].timestamp - entries[0].timestamp)

    if log:
        logger.info(f'There are {len(entries)} entries to go through, covering a span of {total_entry_duration}')

    video_duration_estimate = timedelta(seconds=total_entry_duration.total_seconds() * time_factor)
    # TODO(svioletg): #4 Frame estimate can overshoot sometimes
    frame_estimate: int = round(video_duration_estimate.total_seconds() * fps)
    if log:
        logger.info(f'Video time factor is {time_factor}, final video should be roughly {video_duration_estimate}'
            + f' (~{frame_estimate} frames at {fps} fps)')

    return frame_estimate

def prepare_entries(
        data: str | Path | Sequence[Entry],
        players: Iterable[str] | None = None,
    ) -> list[Entry]:
    """Returns a list of :class:`models.Entry` objects after filtering by players.

    :param data: Either a file path to an SQLite database, a sequence of :class:`models.Entry` objects, or a
        :class:`models.PlayerPositions` object.
    :param players: A list of player UUIDs, of which only the entries for those players will be returned. If empty or
        ``None``, no player filtering is done.
    """
    if isinstance(data, str | Path):
            data = PlayerPositions.from_sql(data).entries

    if players:
        logger.info(f'Filtering data by players: {', '.join(players)}')
    else:
        logger.info('Using data for all players')

    entries: list[Entry] = [entry for entry in data if (not players) or (entry.player_uuid in players)]

    return entries

def prepare_video_writer(
        video_path: str | Path | None,
        size: tuple[int, int],
        *,
        fourcc: str = 'mp4v',
        fps: int = 60,
    ) -> cv2.VideoWriter | None:
    """Returns a :class:`cv2.VideoWriter` with the given options if ``video_path`` is not empty or ``None``."""
    return cv2.VideoWriter(video_path, cv2.VideoWriter.fourcc(*fourcc), fps, size) if video_path else None

def progress_bar(*, disable: bool = True, mofn_m_width: int = 0) -> Progress:
    """Returns a standard render progress bar.

    :param disable: Disables the progress bar if ``True``.
    :param mofn_m_width: How many characters to justify the "M of N" completed display to the right by.
    """
    return Progress(
        TextColumn('[progress.description]{task.description}'),
        TaskProgressColumn('[[info2]{task.percentage:>3.0f}%[/]]'),
        CustomBarColumn(bar_width=None, table_column=Column(ratio=2)),
        TextColumn(
            '[[info2]{task.completed:>' + str(mofn_m_width) +'}/{task.total:<' + str(mofn_m_width) + '}[/]]',
        ),
        console=console,
        transient=True,
        expand=True,
        disable=disable,
    )

def report_frame_estimate_diff(estimate: int, actual: int) -> None:
    """Logs the difference between the given frame estimate and the actual number of frames written."""
    logger.info(f'Wrote {actual} frame(s) to video')
    estimate_diff: int = estimate - actual
    if estimate_diff == 0:
        logger.debug(f'No difference from frame estimate: est. {estimate}, actual {actual}')
    elif estimate_diff > 0:
        diff_pct: float = 1 - (actual / estimate)
        logger.debug(f'Frame estimate overshot by {estimate_diff} (+{diff_pct:.1%})')
    elif estimate_diff < 0:
        diff_pct: float = 1 - (estimate / actual)
        logger.debug(f'Frame estimate undershot by {abs(estimate_diff)} (-{diff_pct:.1%})')

def report_itimes(itimes: list[float], time_started: float, *, level: str = 'INFO') -> None:
    """Logs a summary of iteration time data."""
    logger.log(
        level,
        f'Took {time.perf_counter() - time_started:.4f}s for {len(itimes)} iterations'
        + f' (average iteration {sum(itimes) / len(itimes):.4f}s; min {min(itimes):.4f}s; max {max(itimes):.4f}s)',
    )
