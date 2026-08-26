"""Command-line interface for positionpolling."""
import sys
from argparse import ArgumentParser
from importlib import import_module
from os import get_terminal_size
from pathlib import Path
from typing import Literal, Never, cast

from loguru import logger
from pydantic import ValidationError

from positionpolling import __version__
from positionpolling.const import DEFAULT_LOGS_DIR, NO_COLOR, PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, CliOpt, RenderOpt


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
add_args_from_render_opt(parser_render)

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

    term_width: int = get_terminal_size().columns

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

    logger.debug(f'raw args: {sys.argv}')
    logger.debug(f'parsed args: {args}')

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

            return render_module.cli(render_opt, args)
        case _:
            raise ValueError(f'Invalid action: {args.action!r}')

if __name__ == '__main__':
    sys.exit(main())
