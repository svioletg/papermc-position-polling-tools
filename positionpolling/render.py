"""Common functionality used by most render modules."""
import subprocess
import time
from collections.abc import Iterable, Sequence
from datetime import timedelta
from itertools import pairwise
from math import ceil, floor
from os import devnull
from pathlib import Path
from subprocess import Popen
from threading import Thread
from typing import IO

from geometry import Coord2, Grid2, Tuple4
from loguru import logger
from PIL import Image
from rich.progress import Column, Progress, TaskProgressColumn, TextColumn

from positionpolling.const import console
from positionpolling.models import Entry, PlayerPositions, RenderOpt
from positionpolling.rich import CustomBarColumn
from positionpolling.util import Color, expect, log_stream, require_ffmpeg, void_stream


class FFmpegWriter:
    """Wrapper around an FFmpeg process accepting data on stdin.

    ``__init__`` handles setting up pipes and making sure FFmpeg did not immediately close. If it did,
    :class:`subprocess.CalledProcessError` is raised.
    """

    proc: Popen[bytes]
    """The FFmpeg process."""
    stderr: IO[bytes]
    stdin: IO[bytes]

    def __init__(self, args: Sequence[str], log_level: str | None = 'DEBUG') -> None:
        """Spawns a new FFmpeg process with the given args (see :func:`get_ffmpeg_args`) and ensure it is open.

        If the process exited right after it was started (specifically, the waiting period is currently 0.2 seconds),
        :class:`subprocess.CalledProcessError` is raised with the process' return code, arguments, stdout, and stderr
        contents.

        :param log_level: Log level that FFmpeg's stderr stream will be redirected to. If ``None``, FFmpeg's output is
            discarded. Note that this is separate from the log level of FFmpeg itself; that must be set in ``args``.
        """
        logger.info(f'Run: {' '.join(args)}')
        logger.debug(f'Run: {args}')

        ffmpeg = subprocess.Popen(  # noqa: S603
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )

        logger.debug('Waiting for 0.2s to poll FFmpeg...')
        time.sleep(0.2)

        if ffmpeg.poll() is not None:
            ffout, fferr = expect(ffmpeg.stdout).read().decode('utf-8'), expect(ffmpeg.stderr).read().decode('utf-8')
            logger.error(f'FFmpeg exited immediately with code {ffmpeg.returncode}:\n{fferr}')

            raise subprocess.CalledProcessError(
                ffmpeg.returncode,
                ffmpeg.args,
                ffout,
                fferr,
            )

        if log_level is not None:
            Thread(target=log_stream, args=[ffmpeg.stderr, log_level], kwargs={'name': 'ffmpeg'}, daemon=True).start()
        else:
            Thread(target=void_stream, daemon=True).start()

        self.stderr = expect(ffmpeg.stderr)
        self.stdin = expect(ffmpeg.stdin)

        self.proc = ffmpeg

    def finish(self) -> int:
        """Closes the stdin stream and waits for FFmpeg to exit, returning its exit code."""
        self.stdin.close()

        return self.proc.wait()

def apply_background_image(
        data_img: Image.Image,
        data_grid: Grid2,
        opt: RenderOpt,
    ) -> Image.Image:
    """Apply a background world map to a data render image based on ``opt``.

    If ``opt.bg_img`` is ``None``, ``data_img`` is returned.
    """
    if opt.bg_img is None:
        return data_img

    if opt.bg_img_area is None:
        raise ValueError('opt.bg_img_area cannot be None when opt.bg_img is not None')

    bg = Image.open(opt.bg_img)
    if bg.mode != 'RGBA':
        bg = bg.convert('RGBA')

    bg_img_scale: float = bg.size[0] / (opt.bg_img_area[2] - opt.bg_img_area[0])
    if bg_img_scale != opt.scale:
        bg_scale_div: float = bg_img_scale / opt.scale
        logger.debug(f'Resizing background image: {bg.size} / {bg_scale_div}')
        bg = bg.resize((floor(bg.size[0] / bg_scale_div), floor(bg.size[1] / bg_scale_div)))

    # Get what block the top-left of the heatmap image is at
    bg_world_grid = Grid2(*opt.bg_img_area)

    fit_grid = Grid2(
        min(data_grid.x1, bg_world_grid.x1),
        min(data_grid.y1, bg_world_grid.y1),
        max(data_grid.x2, bg_world_grid.x2),
        max(data_grid.y2, bg_world_grid.y2),
    )

    return paste_with_world_coords(
        resize_canvas(bg, (int(fit_grid.size[0] * opt.scale), int(fit_grid.size[1] * opt.scale))),
        bg_world_grid.as_tuple(int),
        data_img,
        data_grid.as_tuple(int),
    )

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

    |requires-ffmpeg|
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
        '-s', f'{size[0]}x{size[1]}',
        '-r', str(fps),
        '-i', '-',
        '-preset', 'veryfast',
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

    if opt.scale != 1:
        logger.debug(f'Applying render size multiplier {opt.scale}...')

        img_grid = img_grid.map(
            lambda n: n * opt.scale,
            step=data_grid.step * opt.scale,
        ).ceil()

    return img_grid

def resize_canvas(img: Image.Image, size: tuple[int, int], color: Color | int | None = None) -> Image.Image:
    """Returns a new image of the given size with ``img`` centered inside it."""
    if (size[0] > img.size[0]) or (size[1] > img.size[1]):
        canvas = Image.new('RGBA', size, int(color) if color else None)
        canvas.paste(img, ((canvas.size[0] - img.size[0]) // 2, (canvas.size[1] - img.size[1]) // 2))

        return canvas
    else:
        return img.copy().crop((
            img.size[0] - size[0],
            img.size[1] - size[1],
            (img.size[0] - size[0]) + size[0],
            (img.size[1] - size[1]) + size[1],
        ))

def paste_with_world_coords(
        im1: Image.Image,
        im1_area: Tuple4[int],
        im2: Image.Image,
        im2_area: Tuple4[int],
    ) -> Image.Image:
    """Pastes ``im2`` onto ``im1`` in-place, aligned with regards to the world area they cover."""
    im1_world_scale: float = im1.size[0] / (im1_area[2] - im1_area[0])
    im2_world_scale: float = im2.size[0] / (im2_area[2] - im2_area[0])

    if im1_world_scale != im2_world_scale:
        resize_mult: float = im1_world_scale / im2_world_scale
        im2 = im2.resize((int(im2.size[0] * resize_mult), int(im2.size[1] * resize_mult)))

    im1_tl_block = Coord2(im1_area[0], im1_area[1])
    im2_tl_block = Coord2(im2_area[0], im2_area[1])
    im2_br_block = Coord2(im2_area[2], im2_area[3])

    im2_tl_in_im1: Coord2 = (im2_tl_block - im1_tl_block) * im1_world_scale
    im2_br_in_im1: Coord2 = ((im2_br_block - im2_tl_block) * im1_world_scale) + im2_tl_in_im1

    im2_box: Tuple4[int] = (
        *im2_tl_in_im1.as_tuple(ceil),
        *im2_br_in_im1.as_tuple(ceil),
    )

    im1.paste(im2, im2_box, mask=im2)

    return im1

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
    entry_time_span = timedelta(seconds=entries[-1].timestamp - entries[0].timestamp)

    logger.info(
        f'Using {len(entries)} entries,'
        + f' covering a total span of {entry_time_span} ({entry_time_span.total_seconds():.1f}s)',
    )

    return entries

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
