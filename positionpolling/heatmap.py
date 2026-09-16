"""Visualizes player position data as a grid-based heatmap."""
import time
from collections.abc import Iterable, Sequence
from colorsys import hsv_to_rgb
from dataclasses import dataclass
from itertools import pairwise
from math import ceil, floor
from operator import neg
from pathlib import Path
from typing import Literal, cast

import cv2
import numpy as np
from geometry import Coord2, Grid2, Rect
from geometry.util import snap_num
from loguru import logger
from maybetype import Err, Ok, Result
from PIL import Image
from PIL.Image import alpha_composite
from PIL.ImageDraw import ImageDraw

from positionpolling import render
from positionpolling.models import RENDER_OPT_DEFAULT, Entry, RenderOpt
from positionpolling.util import (
    Color,
    ColorSource,
    ask,
    clamp,
    convert_range,
    expect,
    group_by_attr,
    log_progress,
    time_this,
)

type FrameArray = np.ndarray[tuple[int, int, Literal[4]], np.dtype[np.uint8]]

@dataclass
class RegionHueAlpha:
    """Holds hue and alpha values for each region while rendering a heatmap video."""

    hue: float
    """Value from 0 to 1 indicating the hue value for this region."""
    alpha: float
    """Value from 0 to 1 indicating the alpha value for this region."""

    def rgba(self) -> tuple[int, int, int, int]:
        """Return this hue and alpha value as an 8-bit RGBA tuple."""
        return cast('tuple[int, int, int, int]', (
            *(int(n * 255) for n in hsv_to_rgb(self.hue, 1, 1)),
            int(self.alpha * 255),
        ))

def coord_rect(xy: Coord2, data_grid: Grid2) -> Rect:
    """Returns a rectangle tuple this coordinate encompasses based on the given grid and its step."""
    rect_tl = xy.snap_to_grid(data_grid, floor)

    return Rect(*rect_tl, *(rect_tl + data_grid.step))

def get_visited_regions(
        entries: Iterable[Entry],
        data_grid: Grid2,
        players: Iterable[str] | None = None,
    ) -> dict[Rect, dict[str, int]]:
    """Returns a dictionary of region rectangles (based on the given grid) to player visit frequency.

    Visit frequency is given as a dictionary of player UUID strings to how many records of ``entries`` that player
    appeared in.
    """
    if players is None:
        players = {e.player_uuid for e in entries}

    visited_regions: dict[Rect, dict[str, int]] = {}
    for e in entries:
        img_rect = coord_rect(e.xy, data_grid)
        visited_regions.setdefault(img_rect, dict.fromkeys(players, 0))[e.player_uuid] += 1

    return visited_regions

def get_region_player_dist_scores(
        regions: dict[Rect, dict[str, int]],
        target_range: tuple[float, float] = (0, 1),
    ) -> dict[Rect, float]:
    """Calculates player distribution scores (0 to 1) for each of the given regions.

    Scores skew closer to 0 if few players visited it, and closer to 1 if more players visited it similar amounts of
    times.
    """
    region_dists: dict[Rect, list[float]] = {}
    for region, record in regions.items():
        mn, mx = min(record.values()), max(record.values())
        region_dists[region] = [convert_range(i, (mn, mx), (0, 1)) for i in record.values()] \
            if mn != mx else [1] * len(record.values())

    # Assumes every list is the same length, which it should be if it came from get_visited_regions()
    dist_max_sum: int = len(next(iter(region_dists.values())))

    return {
        region:
            convert_range(
                abs(
                    sum(
                        [b - a for a, b in pairwise(dists)]
                        # Include the last pair if more than two items, pairwise won't
                        + ([dists[-1] - dists[-2]] if len(dists) >= 2 else []),  # noqa: PLR2004
                    ),
                ),
                (0, dist_max_sum),
                target_range,
            )
        for region, dists in region_dists.items()
    }

def _heatmap_image(
        entries: list[Entry],
        players: Iterable[str],
        data_grid: Grid2,
        *,
        dist_hue_range: tuple[float, float],
        freq_alpha_range: tuple[float, float],
        opt: RenderOpt,
        bg: Image.Image | ColorSource | None = None,
    ) -> Image.Image:
    logger.info('Gathering region data...')

    visited_regions: dict[Rect, dict[str, int]] = get_visited_regions(entries, data_grid, players)
    region_dist_scores: dict[Rect, float] = get_region_player_dist_scores(visited_regions)
    region_frequencies: dict[Rect, int] = {region:sum(record.values()) for region, record in visited_regions.items()}
    freq_min, freq_max = min(region_frequencies.values()), max(region_frequencies.values())
    if freq_min == freq_max:
        freq_max += 1

    img_grid = data_grid.translate_to((0, 0))

    logger.debug(f'Image grid: {img_grid!r} (size={data_grid.size})')

    logger.info('Assembling heatmap image...')

    img = Image.new('RGBA', (ceil(img_grid.width), ceil(img_grid.height)))

    with render.progress_bar(disable=not opt.progress_bar, mofn_m_width=len(str(len(visited_regions)))) as pbar:
        task_image = pbar.add_task('Assembling heatmap image...', total=len(visited_regions))
        progress_log_thresh_image: float = len(visited_regions) * opt.progress_log_interval

        draw = ImageDraw(img)

        itimes: list[float] = []
        time_started: float = time.perf_counter()

        for entry_n, game_rect in enumerate(visited_regions):
            with time_this(itimes):
                freq = region_frequencies[game_rect]
                dist = region_dist_scores[game_rect]

                img_rect = game_rect.translate_by(data_grid.top_left.map(neg)).resize((-1, -1))
                fill: tuple[int, ...] = (
                    *(int(n * 255) for n in hsv_to_rgb(convert_range(dist, (0, 1), dist_hue_range), 1, 1)),
                    int(convert_range(freq, (freq_min, freq_max), freq_alpha_range) * 255),
                )

                draw.rectangle(img_rect.as_tuple(), fill=fill)
                pbar.update(task_image, advance=1)

                if (opt.progress_log_interval > 0) and (entry_n / len(visited_regions) > progress_log_thresh_image):
                    log_progress(entry_n, len(visited_regions), 'Assembling heatmap image... ')
                    progress_log_thresh_image += opt.progress_log_interval
        del draw
    del pbar

    render.report_itimes(itimes, time_started)

    del itimes, time_started

    if bg is not None:
        logger.info(f'Applying background: {bg!r}')
        bg = bg if isinstance(bg, Image.Image) else Image.new('RGBA', img.size, Color(bg).rgba())
        img = alpha_composite(bg, img)

    logger.info('Image render finished')

    return img

def _mult_within_range(n: float, mult: float, target_range: tuple[float, float]) -> float:
    """Takes ``n`` and applies ``mult`` to it in the context of ``target_range``."""
    return clamp(
        convert_range(
            convert_range(
                n,
                target_range,
                # Convert to a fraction of the range
                (0, 1),
            ) * mult,
            (0, 1),
            # Multiply the fraction as wanted, convert back to intended range
            target_range,
        ),
        target_range,
    )

def _fade_regions(
        img: Image.Image,
        areas: dict[Rect, RegionHueAlpha],
        *,
        ignore: Iterable[Rect] | None = None,
        hue_range: tuple[float, float],
        hue_mult: float = 0.99,
        alpha_range: tuple[float, float],
        alpha_mult: float = 0.99,
    ) -> Image.Image:
    ignore = ignore or ()

    for area, rvalues in areas.items():
        if area in ignore:
            continue
        set_color: bool = False

        # Shift hue toward minimum
        if rvalues.hue != hue_range[0]:
            set_color = True
            rvalues.hue = _mult_within_range(rvalues.hue, hue_mult, hue_range)

        # Shift alpha toward minimum
        if rvalues.alpha != alpha_range[0]:
            set_color = True
            rvalues.alpha = _mult_within_range(rvalues.alpha, alpha_mult, alpha_range)

        if set_color:
            # Apply new color to region
            img.paste(rvalues.rgba(), area.as_tuple(int))

    return img

def _heatmap_video(  # noqa: PLR0915
        entries: list[Entry],
        players: Sequence[str] | set[str],
        data_grid: Grid2,
        video_path: str | Path,
        *,
        dist_hue_range: tuple[float, float],
        freq_alpha_range: tuple[float, float],
        opt: RenderOpt,
        bg: Image.Image | Color | ColorSource | None = None,
    ) -> Path:
    frame_estimate: int = render.get_frame_estimate(entries, time_factor=opt.v_time_factor, fps=opt.v_fps)

    img_grid = data_grid.translate_to((0, 0))
    size: tuple[int, int] = int(img_grid.size[0]), int(img_grid.size[1])

    video: cv2.VideoWriter = expect(render.prepare_video_writer(video_path, size))

    bg = bg if isinstance(bg, Image.Image) else Image.new('RGBA', size, Color(bg or 'black').replace(a=255).rgba())

    mofn_m_width: int = max(
        len(str(frame_estimate)),
        len(str(len(entries))),
    )

    logger.info('Grouping entries by timestamp...')

    by_time: dict[float, list[Entry]] = group_by_attr(entries, 'timestamp', float, ordered=True)

    logger.info('Rendering video...')

    with render.progress_bar(disable=not opt.progress_bar, mofn_m_width=mofn_m_width) as pbar:
        task_data = pbar.add_task('Processing entries...', completed=-1, total=len(entries))
        task_video = pbar.add_task('Writing video...', completed=0, total=frame_estimate)

        progress_log_desc_ljust: int = max(len(s) for s in (
            'Processing entries... ',
            'Writing video... ',
        ))
        progress_log_thresh_data: float = opt.progress_log_interval
        progress_log_thresh_video: float = opt.progress_log_interval

        squares: dict[Rect, RegionHueAlpha] = {}
        players_in_area: dict[Rect, int] = {}
        frame = Image.new('RGBA', size)

        entry_n: int = 0
        frame_n: int = 0

        itimes: list[float] = []
        time_started: float = time.perf_counter()

        for (time_a, batch), (time_b, _) in pairwise(by_time.items()):
            with time_this(itimes):
                players_in_area.clear()
                areas_loaded: list[Rect] = []
                for entry in batch:
                    pbar.update(task_data, advance=1)
                    entry_n += 1

                    rect = coord_rect(entry.xy, data_grid) \
                        .translate_by(data_grid.top_left.map(neg))

                    # Shift hue based on how many players are in this region at the same time
                    players_here = players_in_area[rect] = players_in_area.setdefault(rect, 0) + 1
                    hue: float = convert_range(players_here, (1, len(players)), dist_hue_range)
                    alpha: float = 1.0

                    rvalues: RegionHueAlpha = squares.setdefault(rect, RegionHueAlpha(hue, alpha))
                    rvalues.hue = hue
                    rvalues.alpha = alpha

                    # Seems to be slightly faster to paste than to use ImageDraw.rectangle here
                    frame.paste(rvalues.rgba(), rect.as_tuple(int))

                    areas_loaded.append(rect)

                for _ in range(max(1, round((time_b - time_a) * opt.v_time_factor * opt.v_fps))):
                    # broken out into variables for profiling, would normally just be one line
                    a = alpha_composite(
                        bg,
                        frame,
                    )
                    arr = np.array(
                        a,
                    )
                    vdata = cv2.cvtColor(
                        arr,
                        cv2.COLOR_RGB2BGR,
                    )
                    video.write(
                        vdata,
                    )

                    frame_n += 1
                    pbar.update(task_video, advance=1)
                    _fade_regions(
                        frame,
                        squares,
                        ignore=areas_loaded,
                        hue_range=dist_hue_range,
                        hue_mult=0.99,
                        alpha_range=freq_alpha_range,
                        alpha_mult=0.99,
                    )

                if (opt.progress_log_interval > 0):
                    if entry_n / len(entries) > progress_log_thresh_data:
                        log_progress(entry_n, len(entries), 'Processing entries... '.ljust(progress_log_desc_ljust))
                        progress_log_thresh_data += opt.progress_log_interval

                    if frame_n / frame_estimate > progress_log_thresh_video:
                        log_progress(frame_n, frame_estimate,
                            'Writing video... '.ljust(progress_log_desc_ljust))
                        progress_log_thresh_video += opt.progress_log_interval
        # End entries loop
    del pbar

    logger.info('Video render finished')
    render.report_frame_estimate_diff(frame_estimate, frame_n)
    render.report_itimes(itimes, time_started)

    # End video render

    logger.info(f'Saving video to: {video_path}')
    video.release()
    if opt.v_fix:
        render.fix_video(video_path)

    return Path(video_path)

def heatmap(
        data: str | Path | Sequence[Entry],
        players: Iterable[str] | None = None,
        *,
        video_path: str | Path | None = None,
        dist_hue_range: tuple[float, float] = (0.5, 0),
        freq_alpha_range: tuple[float, float] = (0.1, 0.9),
        region_size: int = 16,
        bg: Image.Image | Color | ColorSource | None = None,
        opt: RenderOpt = RENDER_OPT_DEFAULT,
        confirm: bool = False,
    ) -> Result[Image.Image, str]:
    """Renders a heatmap of which regions of a given size were most visited by players.

    Heatmap videos process data one timestamp at a time and primarily visualize the updates between entries, while the
    heatmap image will take the entire data set into account and is more accurate for a full summary of information.
    The color of each heatmap square—a region—indicates both the frequency at which any number of players visited it
    over the course of the data, and the concentration of players that visited a region on average, the former shown by
    the region's hue, the latter shown by its alpha value, both of which can be configured.

    :param dist_hue_range: Hue range to use for indicating player concentration in a region, skewing toward the second
        value the closer the average amount of players in a given region is to the total number of players that were
        present in the data. Must be decimal values of 0 to 1.
    :param freq_alpha_range: Alpha/opacity range to use for indicating how frequently regions were visited, skewing
        toward the second value the more times any number of players visited it. Must be decimal values of 0 to 1.
    :param region_size: Defaults to the size of a Minecraft chunk (16), specifies how big the areas that are counted for
        the heatmap are, in blocks. Put another way, this specifies heatmap grid's step values.
    :param bg: A background color or existing image to apply to heatmap image onto. If ``None``, the heatmap image is
        left with a transparent background, and the video (if applicable) is given a black background.
    :param confirm: Shows a confirmation prompt before starting the render.
    """
    video_path: Path | None = render.check_video_path(video_path)
    entries: list[Entry] = render.prepare_entries(data, players)
    players: set[str] = {e.player_uuid for e in entries}
    render.get_frame_estimate(entries, time_factor=opt.v_time_factor, fps=opt.v_fps, log=True)

    if len(dist_hue_range) != 2:  # noqa: PLR2004
        raise ValueError(f'Expected two values for dist_hue_range: {dist_hue_range!r}')
    if any((not 0 <= n <= 1) for n in dist_hue_range):
        raise ValueError(f'dist_hue_range values must be in range 0 to 1: {dist_hue_range}')

    if len(freq_alpha_range) != 2:  # noqa: PLR2004
        raise ValueError(f'Expected two values for freq_alpha_range: {freq_alpha_range!r}')
    if any((not 0 <= n <= 1) for n in freq_alpha_range):
        raise ValueError(f'freq_alpha_range values must be in range 0 to 1: {freq_alpha_range}')

    logger.info(f'Heatmap region size: {region_size}')

    # Expand out to make sure every region square is fully visible
    # Bottom right should be expanded out by one more extra region since points will be drawn from top-left
    data_grid = Grid2.from_points((e.xy for e in entries), origin=(0, 0), step=(region_size, region_size)) \
        .map((lambda n: snap_num(n, region_size, floor), lambda n: snap_num(n + 1, region_size, ceil)))

    logger.debug(f'Data grid: {data_grid!r} (size={data_grid.size})')

    if confirm and (ask('Start render? (y/n) ', 'yn') != 'y'):
        logger.info('Render cancelled by user')

        return Err('Cancelled')

    # Start rendering image
    img = _heatmap_image(
        entries,
        players,
        data_grid,
        dist_hue_range=dist_hue_range,
        freq_alpha_range=freq_alpha_range,
        bg=bg,
        opt=opt,
    )

    if video_path:
        _heatmap_video(
            entries,
            players,
            data_grid,
            video_path,
            dist_hue_range=dist_hue_range,
            freq_alpha_range=freq_alpha_range,
            opt=opt,
            bg=bg,
        )

    return Ok(img)
