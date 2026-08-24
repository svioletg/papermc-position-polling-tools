"""Visualizes logged positions as a trail, with lines connecting each pair of points."""
import itertools as it
import time
from argparse import Namespace
from datetime import timedelta
from math import ceil
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import cv2
import numpy as np
from geometry import Coord2, Grid2
from loguru import logger
from maybetype import Err, Ok, Result
from PIL import Image, ImageDraw, ImageEnhance
from rich.progress import Progress, TaskProgressColumn, TextColumn
from rich.table import Column

from positionpolling.cli import abort
from positionpolling.const import console
from positionpolling.models import RENDER_OPT_DEFAULT, Entry, PlayerPositions, RenderOpt
from positionpolling.rich import CustomBarColumn
from positionpolling.util import ask, ask_overwrite, fix_opencv_video, grid_from_entries, log_progress, time_this


def draw_pos_line(
        draw: ImageDraw.ImageDraw,
        pos_grid: Grid2,
        img_grid: Grid2,
        a: Entry,
        b: Entry,
        **kwargs,
    ) -> None:
    """Uses ``draw`` to draw a line from one Minecraft coordinate to another by projecting thme onto ``img_grid``."""
    line_kwargs: dict[str, Any] = {'fill': 0xff0000, 'width': 4} | kwargs

    a_coord = Coord2(a.x, a.z)
    b_coord = Coord2(b.x, b.z)

    draw.line(
        (pos_grid.project(a_coord, img_grid).as_tuple(), pos_grid.project(b_coord, img_grid).as_tuple()),
        **line_kwargs,
    )

def trail(  # noqa: C901, PLR0915
        data: PlayerPositions,
        player: str | None = None,
        *,
        img: Image.Image | None = None,
        desat_per_frame: float = 0.95,
        video_path: str | Path | None = None,
        opt: RenderOpt = RENDER_OPT_DEFAULT,
        confirm: bool = False,
    ) -> Result[tuple[Image.Image, cv2.VideoWriter | None], str]:
    """Generates a "trail" of position logs as both a final image and a video file.

    Returns an ``Ok`` with a tuple of the final image and ``cv2.VideoWriter`` object (if a video was made, otherwise
    ``None``), or an ``Err`` with a string message if the render was cancelled or could not be completed.

    :param data: A :class:`PlayerPositions` instance holding entries to use for the visualization.
    :param player: UUID of the player whose trail should be rendered. If ``None`` and there is only one player key, it
        is used. Otherwise, ``ValueError`` is raised.
    :param img: An optional base image to use. If ``None``, a new image is created.
    :param desat_per_frame: An amount that each previous frame of the video should be desaturated by, creating a fading
        effect as the trail continues. 1 leaves every frame unaffected, 0 makes the previous frame fully greyscale.
    :param video_path: A file path to save the created video to. If ``None``, no video is generated.
    :param opt: Additional rendering options. See: :class:`positionpolling.const.RenderOpt`
    :param confirm: Whether to ask the user for confirmation before beginning the render.
    """
    video_path = Path(video_path).absolute() if video_path else None
    if video_path and not video_path.parent.exists():
        raise FileNotFoundError(f'Directory does not exist: {video_path.parent}')

    data_by_player = data.by_player
    if player is None:
        if len(data_by_player.keys()) == 1:
            player = next(iter(data_by_player.keys()))
        else:
            raise ValueError("'player' is required when position data for multiple players is present")

    logger.info(f'Using data for player: {player}')

    entries = data_by_player[player]
    total_entry_duration = timedelta(seconds=entries[-1].timestamp - entries[0].timestamp)

    logger.info(f'There are {len(entries)} entries to go through, covering a span of {total_entry_duration}')
    frame_estimate: int = 1
    if video_path and opt.v_time_factor:
        video_duration_estimate = timedelta(seconds=total_entry_duration.total_seconds() * opt.v_time_factor)
        # TODO(svioletg): #4 frame estimate overshoots by a fair bit
        frame_estimate: int = round(video_duration_estimate.total_seconds() * opt.v_fps)
        logger.info(f'v_time_factor is {opt.v_time_factor}, final video should be roughly {video_duration_estimate}'
            + f' (~{frame_estimate} frames at {opt.v_fps} fps)')

    datagrid = grid_from_entries(entries)
    imgrid = datagrid.translate_to((0, 0)).round()

    logger.info(f'Image size: {imgrid.size}')

    if confirm and (ask('Start render? (y/n) ', 'yn') != 'y'):
        logger.info('Render cancelled by user')

        return Err('Cancelled')

    img = img or Image.new('RGBA', size=(ceil(imgrid.width), ceil(imgrid.height)))

    video: cv2.VideoWriter | None = None
    if video_path:
        video = cv2.VideoWriter(video_path, cv2.VideoWriter.fourcc(*'mp4v'), opt.v_fps, img.size)

    if video:
        logger.info('Rendering image and video...')
    else:
        logger.info('Rendering image...')

    itimes: list[float] = []
    total_time = time.perf_counter()

    frame = img.copy()
    frame_count: int = 0

    mofn_m_width: int = max(
        len(str(frame_estimate)),
        len(str(len(entries))),
    )

    with Progress(
            TextColumn('[progress.description]{task.description}'),
            TaskProgressColumn('[[info2]{task.percentage:>3.0f}%[/]]'),
            CustomBarColumn(bar_width=None, table_column=Column(ratio=2)),
            TextColumn(
                '[[info2]{task.completed:>' + str(mofn_m_width) +'}/{task.total:<' + str(mofn_m_width) + '}[/]]',
            ),
            console=console,
            transient=True,
            expand=True,
            disable=not opt.progress_bar,
        ) as pbar:
        task_video = pbar.add_task('Writing video...', completed=0, total=frame_estimate) if video_path else None
        task_data = pbar.add_task('Processing entries...', completed=-1, total=len(entries))

        progress_log_desc_ljust: int = max(len(s) for s in (
            'Processing entries... ',
            'Writing video... ',
        ))
        progress_log_thresh_data: float = opt.progress_log_interval
        progress_log_thresh_video: float = opt.progress_log_interval

        for n, (a, b) in enumerate(it.pairwise(entries)):
            logger.trace(f'{n}: (X {a.x:.1f} Z {a.z:.1f}) -> (X {b.x:.1f} Z {b.z:.1f})')
            pbar.update(task_data, advance=1)
            with time_this(itimes):
                color = 'red'

                draw_pos_line(ImageDraw.Draw(frame), datagrid, imgrid, a, b, fill=color)
                if video:
                    duration: int = round((b.timestamp - a.timestamp) * opt.v_fps * opt.v_time_factor) \
                        if opt.v_time_factor else 1

                    while duration:
                        video.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))
                        if task_video is not None:
                            pbar.update(task_video, advance=1)
                        if desat_per_frame < 1:
                            frame = ImageEnhance.Color(frame).enhance(desat_per_frame)
                        frame_count += 1
                        duration -= 1
                else:  # noqa: PLR5501
                    if desat_per_frame < 1:
                        frame = ImageEnhance.Color(frame).enhance(desat_per_frame)

                if (opt.progress_log_interval > 0):
                    if n / len(entries) > progress_log_thresh_data:
                        log_progress(n, len(entries), 'Processing entries... '.ljust(progress_log_desc_ljust))
                        progress_log_thresh_data += opt.progress_log_interval

                    if video_path and (frame_count / frame_estimate > progress_log_thresh_video):
                        log_progress(frame_count, frame_estimate, 'Writing video... '.ljust(progress_log_desc_ljust))
                        progress_log_thresh_video += opt.progress_log_interval

    logger.info('Render finished')
    if video:
        logger.info(f'Wrote {frame_count} frame(s) to video')
        frame_estimate_diff: int = frame_estimate - frame_count
        if frame_estimate_diff == 0:
            logger.debug(f'No difference from frame estimate: est. {frame_estimate}, actual {frame_count}')
        elif frame_estimate_diff > 0:
            diff_pct: float = 1 - (frame_count / frame_estimate)
            logger.debug(f'Frame estimate overshot by {frame_estimate_diff} (+{diff_pct:.1%})')
        elif frame_estimate_diff < 0:
            diff_pct: float = 1 - (frame_estimate / frame_count)
            logger.debug(f'Frame estimate undershot by {abs(frame_estimate_diff)} (-{diff_pct:.1%})')

    logger.info(f'Took {time.perf_counter() - total_time:.4f}s for {len(entries)} data points'
          + f' (average iteration {sum(itimes) / len(itimes):.4f}s; min {min(itimes):.4f}s; max {max(itimes):.4f}s)')

    img = frame

    if video and video_path:
        logger.info(f'Saving video to: {video_path}')
        video.release()
        if opt.v_fix:
            # Log warning and continue on if FFmpeg isn't installed instead of raising an error
            fix_result: Result[Path, CompletedProcess] | None = None
            try:
                fix_result = fix_opencv_video(video_path, video_path, same_file_ok=True)
            except FileNotFoundError as e:
                if 'ffmpeg could not be found' in str(e):
                    logger.warning('FFmpeg is not installed, skipping fix_opencv_video step')
                else:
                    raise

            if fix_result is not None:
                match fix_result:
                    case Ok(dest):
                        logger.info(f'Video reprocessed successfully and saved to {dest}')
                    case Err(proc):
                        logger.error(f'FFmpeg process failed with status {proc.returncode}')
                        logger.info('Video reprocessing failed, the original video is unmodified')

    return Ok((img, video))

def cli(render_opt: RenderOpt, args: Namespace) -> int:  # noqa: C901
    """Function to be called when using the CLI interface launched by :func:`positionpolling.cli.main`.

    Returns an exit code.
    """
    data = PlayerPositions.from_sql(args.source)
    player: str | None = args.player
    img_dest: Path | None = args.out and args.out.absolute()
    video_dest: Path | None = args.video and args.video.absolute()
    desat_per_frame: float = args.desat_per_frame
    auto_confirm: bool = args.yes

    if player and (player not in data.by_player):
        abort(f'Found no entries in the given data for player: {player}')

    if img_dest is video_dest is None:
        abort('One or both of "--out" or "--video" must be specified.')

    if img_dest and img_dest.is_dir():
        abort(f'--out option value exists and is a directory: {img_dest}')
    if video_dest and video_dest.is_dir():
        abort(f'--video option value exists and is a directory: {video_dest}')

    for path in (img_dest, video_dest):
        if path is None:
            continue

        if (not auto_confirm) and path.exists() and not ask_overwrite(path):
            abort('Aborting.')

    result = trail(
        data,
        player,
        desat_per_frame=desat_per_frame,
        video_path=video_dest,
        opt=render_opt,
        confirm=not auto_confirm,
    )

    match result:
        case Err(e):
            # Cancellation is logged, no reason for a redundant error message
            if e == 'Cancelled':
                return 1
            abort(f'Render failed: {e}')
        case Ok((img, _video_writer)):
            if img_dest:
                logger.info(f'Saving image to: {img_dest}')
                img.save(img_dest)

    return 0
