"""Common functionality used by most render modules."""
import time
from collections.abc import Iterable, Sequence
from itertools import pairwise
from os import devnull
from pathlib import Path
from subprocess import CompletedProcess
from typing import cast

import cv2
from geometry import Grid2
from loguru import logger
from maybetype import Err, Ok, Result
from rich.progress import Column, Progress, TaskProgressColumn, TextColumn

from positionpolling.const import console
from positionpolling.models import Entry, PlayerPositions, RenderOpt
from positionpolling.rich import CustomBarColumn
from positionpolling.util import fix_opencv_video, require_ffmpeg


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

def ffmpeg_size_in_range(size: tuple[int, int]) -> bool:
    """Returns whether the given size is within FFmpeg's picture size limit."""
    return ((size[0] * 8 + 1024) * size[1] + 128) < (2 ** 31 - 1)

def get_ffmpeg_args(
        video_path: str | Path,
        size: tuple[int, int],
        *,
        fps: int,
        crf: int = 23,
        log_level: str = 'info',
    ) -> tuple[str, ...]:
    """Returns a tuple of arguments to spawn an FFmpeg process reading RGBA video data from stdin.

    This function will call :func:`util.require_ffmpeg`.
    """
    # If /dev/null is given FFmpeg needs a format specified
    out_format_args: tuple[str, ...] = ('-f', 'null') if str(video_path) == devnull else ()

    return (
        require_ffmpeg(),
        '-y',
        '-v', log_level,
        '-stats_period', '2',
        '-f', 'rawvideo',
        '-pix_fmt', 'rgba',
        '-vsync', '0',
        '-s', f'{size[0]}x{size[1]}',
        '-r', str(fps),
        '-i', '-',
        '-crf', str(crf),
        *out_format_args,
        str(video_path),
    )

def get_frame_estimate(
        entries: Sequence[Entry],
        *,
        time_factor: float,
        fps: int,
        log: bool = False,
    ) -> tuple[int, float]:
    """Estimate how many frames long a video render of these entries should be based on the given time factor and fps.

    Returns a tuple of the estimated frames and the estimated duration of the video in seconds. If ``time_factor`` is 0,
    the estimate returned is for one frame per unique entry timestamp.
    """
    # Iterating over the whole thing should almost always be fully accurate, it's somewhat slow but in most situations
    # this function shouldn't be getting called many times over

    if time_factor > 0:
        frame_estimate: int = sum(
            round(diff * time_factor * fps)
            for a, b in pairwise(entries)
            if (diff := b.timestamp - a.timestamp) != 0
        )
    else:
        frame_estimate: int = len({e.timestamp for e in entries}) + 1

    video_duration_estimate: float = frame_estimate / fps
    if log:
        logger.info(f'Video time factor is {time_factor}, final video should be roughly {video_duration_estimate}'
            + f' (~{frame_estimate} frames at {fps} fps)')

    return (frame_estimate, video_duration_estimate)

def get_image_grid(data_grid: Grid2, opt: RenderOpt) -> Grid2:
    """Returns a grid to be referenced for image rendering of a position log data grid.

    The resulting grid has an ``origin`` of ``(0, 0)``.
    """
    img_grid = data_grid.translate_to((0, 0), origin=(0, 0))

    if isinstance(opt.size, tuple):
        logger.debug(f'Applying render size tuple {opt.size}...')

        iw, ih = opt.size
        stretch_x, stretch_y = (iw / data_grid.width, ih / data_grid.height)
        img_grid = Grid2.from_size(
            opt.size,
            step=(data_grid.step.x * stretch_x, data_grid.step.y * stretch_y),
            origin=(0, 0),
        )
    elif isinstance(opt.size, (int, float)):
        logger.debug(f'Applying render size multiplier {opt.size}...')

        img_grid = img_grid.map(
            lambda n: n * cast('float', opt.size), # cast for ty false positive here
            step=data_grid.step * opt.size,
        ).ceil()

    return img_grid

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
        size: tuple[float, float],
        *,
        fourcc: str = 'mp4v',
        fps: int = 60,
    ) -> cv2.VideoWriter | None:
    """Returns a :class:`cv2.VideoWriter` with the given options if ``video_path`` is not empty or ``None``."""
    return cv2.VideoWriter(
        video_path,
        cv2.VideoWriter.fourcc(*fourcc),
        fps,
        (int(size[0]), int(size[1])),
    ) if video_path else None

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
    logger.opt(depth=1).info(f'Wrote {actual} frame(s) to video')
    estimate_diff: int = estimate - actual
    if estimate_diff == 0:
        logger.opt(depth=1).debug(f'No difference from frame estimate: est. {estimate}, actual {actual}')
    elif estimate_diff > 0:
        diff_pct: float = 1 - (actual / estimate)
        logger.opt(depth=1).debug(f'Frame estimate overshot by {estimate_diff} (+{diff_pct:.1%})')
    elif estimate_diff < 0:
        diff_pct: float = 1 - (estimate / actual)
        logger.opt(depth=1).debug(f'Frame estimate undershot by {abs(estimate_diff)} (-{diff_pct:.1%})')

def report_itimes(itimes: list[float], time_started: float, *, level: str = 'INFO') -> None:
    """Logs a summary of iteration time data."""
    logger.opt(depth=1).log(
        level,
        f'Took {time.perf_counter() - time_started:.4f}s for {len(itimes)} iterations'
        + f' (average iteration {sum(itimes) / len(itimes):.4f}s; min {min(itimes):.4f}s; max {max(itimes):.4f}s)',
    )
