"""Command-line interface for positionpolling."""
import json
import sys
import time
from argparse import ArgumentParser, BooleanOptionalAction
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from enum import StrEnum
from importlib import import_module
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Literal, Never, TypeAliasType, cast, get_args, get_origin, overload

from loguru import logger
from pydantic.fields import FieldInfo
from tabulate import tabulate

from positionpolling import __version__
from positionpolling.const import DEFAULT_LOGS_DIR, NO_COLOR, PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, CliOpt, PlayerPositions, RenderOpt
from positionpolling.util import try_next


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
    for name, fld in cast('dict[str, FieldInfo]', RenderOpt.model_fields).items():
        kwargs: dict[str, Any] = {'dest': name, 'help': (fld.description or '').replace('%', '%%')}

        typ = fld.annotation
        while t_args := get_args(typ):
            if t_args:
                t_origin = get_origin(typ)
                # Making an assumption here that we only ever care about the first argument of a union
                # RenderOpt really shouldn't have any union types that aren't T | None, so this is fine
                typ = t_args[0] if t_origin in [Annotated, UnionType] else t_origin

            if isinstance(typ, TypeAliasType):
                typ = typ.__value__

        if typ is bool:
            kwargs['action'] = BooleanOptionalAction
        elif typ in [tuple, list]:
            kwargs['type'] = comma_split
        else:
            kwargs['type'] = typ

        cli_meta: CliOpt = try_next(i for i in fld.metadata if isinstance(i, CliOpt)) \
            or CliOpt([f'--{name.replace('_', '-')}'], kwargs)

        parser.add_argument(*cli_meta.names, **kwargs | cli_meta.kwargs)

    return parser

@overload
def comma_split[T](s: str, fn: Callable[[list[str]], T], *, strip: bool = False) -> T: ...
@overload
def comma_split[T](s: str, fn: None = None, *, strip: bool = False) -> list[str]: ...
def comma_split[T](s: str, fn: Callable[[list[str]], T] | None = None, *, strip: bool = False) -> T | list[str]:
    """Splits a string by commas and returns ``typ`` called with the split list.

    If ``typ`` is ``None``, the list is returned. Strips whitespace if ``strip=True``.
    """
    split: list[str] = s.split(',') if not strip else [i.strip() for i in s.split(',')]

    return split if not fn else fn(split)

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
parser_inspect.add_argument('--out', '-o', dest='inspect_out', type=str,
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
def main() -> int:  # noqa: C901, D103, PLR0915
    setup_logger('ERROR')

    # Parse args
    args = main_parser.parse_args()
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

    logger.trace(f'raw args: {sys.argv}')
    logger.trace(f'parsed args: {args}')

    if len(sys.argv) == 1:
        main_parser.print_help()

        return 0

    if not args.action:
        abort(
            f'[warn]Missing action. Run "{Path(sys.argv[0]).name} --help" to see a list of options.[/]',
            markup=False,
        )

    logger.info(f'{PACKAGE_ROOT.name} v{__version__}')
    logger.debug(f'stdout log level is {log_level.name}')
    if log_file_return:
        log_file = log_file_return[1]
        logger.debug(f'Log file: {log_file}')

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
                    players: list[str] | None = args.player
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

            render_opt: RenderOpt = (RenderOpt.from_json(render_json) if render_json else RENDER_OPT_DEFAULT).replace(
                {k:v for k, v in args.__dict__.items() if v is not None},
            )

            logger.debug(repr(render_opt))
            logger.info('\n' + render_opt.display())

            render_type: str = args.render_type
            render_modpath: str = f'{PACKAGE_ROOT.name}.{render_type}'
            logger.debug(f'Importing render module for "{render_type}" using path {render_modpath}')
            render_module = import_module(render_modpath)

            return render_module.cli(render_opt, args)
        case _:
            raise ValueError(f'Invalid action: {args.action!r}')

if __name__ == '__main__':
    sys.exit(main())
