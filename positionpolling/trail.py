"""Visualizes logged positions as a trail, with lines connecting each pair of points."""
import itertools as it
import time
from argparse import Namespace
from collections.abc import Sequence
from math import ceil
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from geometry import Coord2, Grid2
from loguru import logger
from maybetype import Err, Ok, Result
from PIL import Image, ImageDraw, ImageEnhance

from positionpolling import render
from positionpolling.cli import abort
from positionpolling.models import RENDER_OPT_DEFAULT, Entry, PlayerPositions, RenderOpt
from positionpolling.util import ask, ask_overwrite, grid_from_entries, log_progress, time_this


def draw_pos_line(
        draw: ImageDraw.ImageDraw,
        pos_grid: Grid2,
        img_grid: Grid2,
        a: Coord2,
        b: Coord2,
        **kwargs,
    ) -> None:
    """Uses ``draw`` to draw a line from one Minecraft coordinate to another by projecting them onto ``img_grid``."""
    line_kwargs: dict[str, Any] = {'fill': 0xff0000, 'width': 4} | kwargs

    draw.line(
        (pos_grid.project(a, img_grid).as_tuple(), pos_grid.project(b, img_grid).as_tuple()),
        **line_kwargs,
    )

# TODO(svioletg): #6 Support multiple player trails
def trail(  # noqa: C901, PLR0915
        data: str | Path | Sequence[Entry],
        players: list[str] | None = None,
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
    video_path: Path | None = render.check_video_path(video_path)
    entries: list[Entry] = render.prepare_entries(data, players)
    frame_estimate: int = render.get_frame_estimate(
        entries,
        time_factor=opt.v_time_factor,
        fps=opt.v_fps,
        log=True,
    )[0] if video_path else 1

    datagrid = grid_from_entries(entries)
    imgrid = datagrid.translate_to((0, 0)).round()

    logger.info(f'Image size: {imgrid.size}')

    if confirm and (ask('Start render? (y/n) ', 'yn') != 'y'):
        logger.info('Render cancelled by user')

        return Err('Cancelled')

    img = img or Image.new('RGBA', size=(ceil(imgrid.width), ceil(imgrid.height)))

    video: cv2.VideoWriter | None = render.prepare_video_writer(video_path, img.size, fps=opt.v_fps)

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

    with render.progress_bar(disable=not opt.progress_bar, mofn_m_width=mofn_m_width) as pbar:
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

                draw_pos_line(ImageDraw.Draw(frame), datagrid, imgrid, a.xy, b.xy, fill=color)
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
        render.report_frame_estimate_diff(frame_estimate, frame_count)

    logger.info(f'Took {time.perf_counter() - total_time:.4f}s for {len(entries)} data points'
          + f' (average iteration {sum(itimes) / len(itimes):.4f}s; min {min(itimes):.4f}s; max {max(itimes):.4f}s)')

    img = frame

    if video and video_path:
        logger.info(f'Saving video to: {video_path}')
        video.release()
        if opt.v_fix:
           render.fix_video(video_path)

    return Ok((img, video))

def cli(render_opt: RenderOpt, args: Namespace) -> int:  # noqa: C901
    """Function to be called when using the CLI interface launched by :func:`positionpolling.cli.main`.

    Returns an exit code.
    """
    data = PlayerPositions.from_sql(args.input)
    players: list[str] | None = args.player
    img_dest: Path | None = args.out and args.out.absolute()
    video_dest: Path | None = args.video and args.video.absolute()
    desat_per_frame: float = args.desat_per_frame
    auto_confirm: bool = args.yes

    for p in players or []:
        if p not in data.by_player:
            abort(f'Found no entries in the given data for player: {p}')

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
        data.entries,
        players,
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
