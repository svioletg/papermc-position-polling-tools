"""Command-line interface for positionpolling."""
import sys
from argparse import ArgumentParser, BooleanOptionalAction
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Literal, Never, cast, get_args, get_origin, overload

from loguru import logger
from pydantic.fields import FieldInfo

from positionpolling import __version__
from positionpolling.const import DEFAULT_LOGS_DIR, NO_COLOR, PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, CliOpt, RenderOpt
from positionpolling.util import try_next


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
    parser.add_argument('--render-json', '-j', type=Path, metavar='PATH',
        help='Path to a JSON file defining render options to use. Individual render options will override these'
            + ' settings. If a file named "render.json" exists in the current directory and this option was not used,'
            + ' it will be automatically used for this value.')

    for name, fld in cast('dict[str, FieldInfo]', RenderOpt.model_fields).items():
        kwargs: dict[str, Any] = {'dest': name, 'help': fld.description}

        typ = fld.annotation if get_origin(fld.annotation) not in [Annotated, UnionType] \
            else get_args(fld.annotation)[0]

        if typ is bool:
            kwargs['action'] = BooleanOptionalAction
        elif typ in [tuple, list]:
            kwargs['type'] = comma_split

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

parser_render = add_args_from_render_opt(subparsers.add_parser('render'))

parser_render_trail = ArgumentParser(add_help=False)
parser_render_trail.add_argument('source', type=str,
    help='Path or URL to the SQL database to use.')
parser_render_trail.add_argument('--out', '-o', type=Path, required=False,
    help='Where to save the rendered image.')
parser_render_trail.add_argument('--video', '-v', type=Path, required=False,
    help='Whether to render a video, and if so, where to save it to. Video rendering is skipped.')
parser_render_trail.add_argument('--player', type=str,
    help='UUID of the player whose data should be used.')
parser_render_trail.add_argument('--desat-per-frame', type=float, default=0.95,
    help='An amount that each previous frame of the video should be desaturated by, creating a fading effect as the'
        + ' trail continues. , 0 makes the previous frame fully greyscale.')

render_arg_parsers: dict[str, ArgumentParser] = {
    'trail': parser_render_trail,
}

render_subparsers = parser_render.add_subparsers(dest='render_type', required=True)

for k, v in render_arg_parsers.items():
    render_subparsers.add_parser(k, parents=[v])

@logger.catch(onerror=lambda _: sys.exit(1))
def main() -> int:  # noqa: D103
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
    _, (log_file_return) = setup_logger(
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
