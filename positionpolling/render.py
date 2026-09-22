"""Common functionality used by most render modules."""
import time
from collections.abc import Iterable, Sequence
from itertools import pairwise
from os import devnull
from pathlib import Path

from geometry import Coord2, Grid2, Tuple4
from loguru import logger
from PIL import Image
from rich.progress import Column, Progress, TaskProgressColumn, TextColumn

from positionpolling.const import console
from positionpolling.models import Entry, PlayerPositions, RenderOpt
from positionpolling.rich import CustomBarColumn
from positionpolling.util import Color, require_ffmpeg


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

    if opt.scale != 1:
        logger.debug(f'Applying render size multiplier {opt.scale}...')

        img_grid = img_grid.map(
            lambda n: n * opt.scale, # cast for ty false positive here
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
        *im2_tl_in_im1.as_tuple(int),
        *im2_br_in_im1.as_tuple(int),
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
