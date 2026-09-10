"""Command-line interface for positionpolling."""
import json
import sys
import time
from argparse import ArgumentParser, BooleanOptionalAction
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from importlib import import_module
from os import get_terminal_size
from pathlib import Path
from typing import Literal, Never, cast

from loguru import logger
from pydantic import ValidationError
from tabulate import tabulate

from positionpolling import __version__
from positionpolling.const import DEFAULT_LOGS_DIR, NO_COLOR, PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, CliOpt, PlayerPositions, RenderOpt
from positionpolling.util import parse_players

DEFAULT_PLAYER_MAP_PATH: Path = Path('players.json')

class InspectFormat(StrEnum):
    """Choices for the ``inspect`` command's ``--format`` option."""

    CSV = 'csv'
    JSON = 'json'
    TABLE = 'table'

def abort(err: str | Exception, *, log: bool = True, markup: bool = True, status: int = 1) -> Never:
    """Print an error message or exception without a full traceback and exit with code ``status``.

    :param markup: If ``True`` and ``log`` is ``False``, wrap the message in ``[err][/]`` markup before printing,
        otherwise print the string as-is.
    :param log: If ``True``, the message is logged with ``logger.error()``. Otherwise, the message is printed with the
        ``rich`` console.
    """
    msg = err if isinstance(err, str) else f'{err.__class__.__name__}: {err}'

    if log:
        logger.error(msg)
    else:
        console.print(f'[err]{msg}[/]' if markup else msg)

    sys.exit(status)

def add_args_from_render_opt(parser: ArgumentParser) -> ArgumentParser:
    """Adds arguments to an ``ArgumentParser`` object from the fields in :class:`models.RenderOpt`.

    Returns the passed parser.
    """
    for name in RenderOpt.model_fields:
        cli_meta: CliOpt = RenderOpt.cli_meta()[name]
        parser.add_argument(*cli_meta.names, **cli_meta.kwargs)

    return parser

def cli_format_validation_error(exc: ValidationError) -> str:
    """Formats a ``pydantic.ValidationError`` into a string for CLI output."""
    message: list[str] = []
    for e in exc.errors():
        field: str = cast('str', e['loc'][0])
        names: str = '/'.join(RenderOpt.cli_meta()[field].names)
        message.append(f'{names}: {e['msg']}\n    (value: {e['input']!r})')

    return '\n'.join(message)

def format_inspect_data(table: Iterable[Iterable[object]], fmt: str | InspectFormat, headers: Sequence[str] = ()) \
    -> str:
    """Formats table data into an output string for the ``inspect`` command.

    When formatting as JSON, the tabular data will be transformed into a list of objects as such, with the values of
    ``headers`` being used for each object's keys:

    >>> data = [(1, 'Red'), (2, 'Green'), (3, 'Blue')]
    >>> assert format_inspect_data(data, 'json', headers=('number', 'color')) == '''
    ... [
    ...     {
    ...         "number": 1,
    ...         "color": "Red"
    ...     },
    ...     {
    ...         "number": 2,
    ...         "color": "Green"
    ...     },
    ...     {
    ...         "number": 3,
    ...         "color": "Blue"
    ...     }
    ... ]
    ... '''.strip()

    """
    fmt = InspectFormat(fmt)

    if fmt == InspectFormat.TABLE:
        out_str = tabulate(
            table,
            headers=headers,
            tablefmt='plain',
            numalign='left',
        )
    elif fmt == InspectFormat.CSV:
        out_str = '\n'.join(
            ','.join(map(str, row))
            for row in (headers, *table)
        )
    elif fmt == InspectFormat.JSON:
        out_str = json.dumps([OrderedDict(zip(headers, row, strict=True)) for row in table], indent=4)

    return out_str

def parse_players_or_abort(players: list[str], player_map: Mapping[str, str]) -> set[str]:
    """Returns a set of player UUIDs from a list of names or UUIDs using the given map, aborting for missing keys."""
    missing_players: list[str] = []
    # Make this a set to ignore possible duplicates if two keys point to the same UUID
    parsed_players: set[str] = set(parse_players(
        players,
        player_map,
        missing=missing_players.append,
    ))
    if missing_players:
        abort('Specified player(s) were not found in the player map and are not UUIDs: '
            + ', '.join(missing_players))

    return parsed_players

main_parser = ArgumentParser()
main_parser.add_argument('--version', '-V', action='store_true',
    help='Shows the installed version and exits.')
main_parser.add_argument('--log-level', '-l', type=lambda s: s.upper(), choices=[i.name for i in LogLevel],
    default='INFO',
    help='The logging level for this session. "DEBUG" shows more output and can be useful for diagnosing issues.'
        + ' "TRACE" is the most verbose setting and may result in a very large volume of logs, only use this if'
        + ' "DEBUG" hasn\'t helped enough. Log files always use level DEBUG, or TRACE if it is specified.')
main_parser.add_argument('--logfile', dest='log_file', type=Path, default=DEFAULT_LOGS_DIR,
    help='Log file path to use for this run, or a directory to save this log to. This path will be treated as a'
        + ' directory if it does not end in ".log". If given a directory, a log file is created based on the'
        + " current time and date and stored inside it. Defaults to the package's logs directory.")
main_parser.add_argument('--no-logfile', dest='log_file', action='store_false',
    help='Disables file logging; logs will only be sent to stdout. A log file may still be created if any errors'
        + ' occur before arguments can be parsed.')
main_parser.add_argument('--no-color', action='store_true',
    help='Disables colored terminal output. This overrides the value set by MCPOSLOG_NO_COLOR.')
main_parser.add_argument('--yes', '-y', action='store_true',
    help='Skips confirmation prompts.')
main_parser.add_argument('--player-map', type=Path, metavar='PATH',
    help='Path to a JSON file mapping player names to UUIDs, allowing those names to be used for --player option'
        + ' values instead of full UUIDs. Any values given to --player that are not in the UUID4 format are assumed to'
        + ' be keys to use for this map. If a file named "players.json" exists in the current directory and this'
        + ' option was not used, it will be automatically used for this value.')

subparsers = main_parser.add_subparsers(dest='action', required=False)

parser_render = subparsers.add_parser('render')
parser_render.add_argument('--render-json', '-j', type=Path, metavar='PATH',
    help='Path to a JSON file defining render options to use. Individual render options will override these'
        + ' settings. If a file named "render.json" exists in the current directory and this option was not used,'
        + ' it will be automatically used for this value.')

add_args_from_render_opt(parser_render)

parser_render_trail = ArgumentParser(add_help=False)
parser_render_trail.add_argument('--input', '-i', type=str, required=True,
    help='Path or URL to the SQL database to use.')
parser_render_trail.add_argument('--out', '-o', type=Path, required=False,
    help='Where to save the rendered image.')
parser_render_trail.add_argument('--video', '-v', type=Path, required=False,
    help='Whether to render a video, and if so, where to save it to. Video rendering is skipped.')
parser_render_trail.add_argument('--player', type=str, nargs='*', action='extend',
    help='One or more player UUIDs whose data should be used.')
parser_render_trail.add_argument('--desat-per-frame', type=float, default=0.95,
    help='An amount that each previous frame of the video should be desaturated by, creating a fading effect as the'
        + ' trail continues. , 0 makes the previous frame fully greyscale.')

render_arg_parsers: dict[str, ArgumentParser] = {
    'trail': parser_render_trail,
}

render_subparsers = parser_render.add_subparsers(dest='render_type', required=True)

for k, v in render_arg_parsers.items():
    render_subparsers.add_parser(k, parents=[v])

parser_inspect = subparsers.add_parser('inspect')
parser_inspect.add_argument('--input', '-i', dest='source', type=str, required=True,
    help='Path or URL to the SQL database to use.')
parser_inspect.add_argument('--out', '-o', dest='inspect_out', type=Path,
    help='File path to save output to. If omitted, output is printed to screen and not saved to disk.')
parser_inspect.add_argument('--format', '-f', dest='inspect_out_format', type=str.lower,
    choices=[i.value for i in InspectFormat], default=InspectFormat.TABLE,
    help='How to format the output data.')

inspect_subparsers = parser_inspect.add_subparsers(dest='inspect_action', required=True)
parser_inspect_count = ArgumentParser(add_help=False)
parser_inspect_count.add_argument('--player', type=str, nargs='*', action='extend',
    help='UUID of the player whose entries will be counted. Omit to count all entries.')
parser_inspect_count.add_argument('--total', dest='count_total', action=BooleanOptionalAction, default=True,
    help='Whether to include a sum total of every specified players\' entry counts, included as an additional "total"'
        + ' player.')
parser_inspect_count.add_argument('--sort', '-s', dest='count_sort', type=lambda s: s.split(':', maxsplit=1),
    metavar='{entries,player}', default='entries:d',
    help='How to sort the resulting player entry counts. "player" sorts by player names in alphabetical order,'
        + ' "entries" sorts by entry count (most entries first). Sorted in ascending order by default; add ":d" to the'
        + ' end of the value to sort descending.')

inspect_subparsers.add_parser('count', parents=[parser_inspect_count])

@logger.catch(onerror=lambda _: sys.exit(1))
def main(argv: list[str] | None = None) -> int:  # noqa: C901, D103, PLR0915
    setup_logger('ERROR')

    # Check None explicitly since an empty list is valid to use
    # Omit the command name since we're not using it and so usage of sys.argv vs. a passed list will be consistent
    argv = sys.argv[1:] if argv is None else argv

    term_width: int = get_terminal_size().columns if sys.stdout.isatty() else 80

    # Parse args
    args = main_parser.parse_args(argv)
    no_color: bool = args.no_color

    console.no_color = no_color or NO_COLOR

    if args.version:
        console.print(__version__)

        return 0

    log_level = LogLevel[args.log_level]
    log_file: Path | Literal[False] = args.log_file

    # Start logging
    _, log_file_return = setup_logger(
        log_level,
        min(log_level, LogLevel.DEBUG),
        log_path=log_file or None,
        no_color=no_color or NO_COLOR,
    )

    logger.debug(f'raw args: {argv}')
    logger.debug(f'parsed args: {args}')

    if (len(argv) == 0) or (not args.action):
        if len(argv) > 0:
            # If the command was invoked with no arguments or options at all, just show the help message and skip this
            console.print(f'[err]Missing an action, must choose one of: {', '.join(subparsers.choices)}[/]')

        main_parser.print_help()

        return 2

    logger.info(f'{PACKAGE_ROOT.name} v{__version__}')
    logger.debug(f'stdout log level is {log_level.name}')
    if log_file_return:
        log_file = log_file_return[1]
        logger.debug(f'Log file: {log_file}')

    # Get player name -> UUID map
    player_map_path: Path | None = None

    if args.player_map:
        if not args.player_map.is_file():
            abort(f'--player-map: not a file or does not exist: {args.player_map}')
        player_map_path = args.player_map
        logger.info(f'Using player map: {player_map_path}')
    elif DEFAULT_PLAYER_MAP_PATH.is_file():
        player_map_path = DEFAULT_PLAYER_MAP_PATH
        logger.info(f'Using player map: {player_map_path}')

    player_map: dict[str, str] = json.loads(player_map_path.read_text('utf-8')) if player_map_path else {}

    match args.action:
        case 'inspect':
            logger.info(f'Loading position data from: {args.source}')
            ta = time.perf_counter()
            data = PlayerPositions.from_sql(args.source)
            logger.debug(f'Load took {time.perf_counter() - ta:.8f}s')
            del ta

            out_format = InspectFormat(args.inspect_out_format)

            match args.inspect_action:
                case 'count':
                    players: set[str] = parse_players_or_abort(args.player or [], player_map)

                    table: list[tuple[str, int]] = []
                    total: int = 0

                    for player in players or data.by_player:
                        count: int = len(data.by_player.get(player, ()))
                        table.append((player, count))
                        total += count

                    sorting: str = args.count_sort[0]
                    sort_reverse: bool = args.count_sort[1] == 'd' if len(args.count_sort) > 1 else False

                    match sorting:
                        case 'player':
                            table.sort(key=lambda kv: kv[0], reverse=sort_reverse)
                        case 'entries':
                            table.sort(key=lambda kv: kv[1], reverse=sort_reverse)
                        case _:
                            raise ValueError(f'Invalid sort choice: {sorting!r}')

                    if args.count_total:
                        table.append(('total', total))

                    out_str: str = format_inspect_data(table, out_format, ('Player', 'Entries'))

                    if args.inspect_out:
                        dest: Path = Path(args.inspect_out).absolute()
                        logger.info(f'Saving output to: {dest}')
                        dest.write_text(out_str, 'utf-8')
                    else:
                        # Use plain print instead of the rich console, don't want anything interfering with output meant
                        # to be parseable
                        print(out_str)  # noqa: T201

                    return 0
                case _:
                    raise ValueError(f'Invalid inspect action: {args.inspect_action!r}')
        case 'render':
            render_json: Path | None = args.render_json

            # Automatically use file called "render.json" if present in current directory
            if (render_json is None) and not (render_json := Path.cwd() / ('render.json')).is_file():
                render_json = None

            logger.debug('Getting render options...')
            logger.debug(f'RenderOpt JSON file: {render_json or '<none>'}')

            try:
                # Separate these steps out for clarity
                _base_render_opt: RenderOpt = RenderOpt.from_json(render_json) if render_json else RENDER_OPT_DEFAULT
                render_opt: RenderOpt = _base_render_opt.replace(
                    {k:v for k, v in args.__dict__.items() if v is not None},
                )

                del _base_render_opt
            except ValidationError as e:
                logger.opt(exception=e).debug('RenderOpt validation failed; full traceback below')
                logger.error('Failed to parse some render options')
                if log_file:
                    logger.error(f'Full traceback at: {log_file}')
                console.print('-' * min(term_width, round(term_width * 0.75)))

                abort(cli_format_validation_error(e), log=False)

            logger.debug(repr(render_opt))
            logger.info('\n' + render_opt.display())

            render_type: str = args.render_type
            render_modpath: str = f'{PACKAGE_ROOT.name}.{render_type}'
            logger.debug(f'Importing render module for "{render_type}" using path {render_modpath}')
            render_module = import_module(render_modpath)

            if args.player is not None:
                args.player = list(parse_players_or_abort(args.player or [], player_map))

            return render_module.cli(render_opt, args)
        case _:
            raise ValueError(f'Invalid action: {args.action!r}')

if __name__ == '__main__':
    sys.exit(main())
