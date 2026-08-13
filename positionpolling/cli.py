"""Command-line interface for positionpolling."""
import sys
from argparse import ArgumentParser, BooleanOptionalAction
from importlib import import_module
from pathlib import Path
from typing import Any, Never, cast

from loguru import logger
from pydantic.fields import FieldInfo

from positionpolling import __version__
from positionpolling.const import DEFAULT_LOGS_DIR, PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, CliOpt, RenderOpt
from positionpolling.util import try_next

parser_render_trail = ArgumentParser(add_help=False)
parser_render_trail.add_argument('source', type=str,
    help='Path or URL to the SQL database to use.')
parser_render_trail.add_argument('--out', '-o', type=Path, required=True,
    help='Where to save the rendered video.')
parser_render_trail.add_argument('--player', type=str,
    help='UUID of the player whose data should be used.')
parser_render_trail.add_argument('--desat-per-frame', type=float, default=0.95,
    help='An amount that each previous frame of the video should be desaturated by, creating a fading effect as the'
        + ' trail continues. , 0 makes the previous frame fully greyscale.')

render_arg_parsers: dict[str, ArgumentParser] = {
    'trail': parser_render_trail,
}

def abort(err: str | Exception, *, log: bool = False, markup: bool = True, status: int = 1) -> Never:
    """Print an error message or exception without a full traceback and exit with code ``status``.

    :param markup: If ``True``, wrap the message in ``[err][/]`` markup before printing, otherwise prints it as-is.
        Ignored if ``log`` is ``True``, in which case markup is never added.
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
            + ' settings.')

    for name, fld in cast('dict[str, FieldInfo]', RenderOpt.model_fields).items():
        kwargs: dict[str, Any] = {'dest': name, 'help': fld.description}

        if fld.annotation is bool:
            kwargs['action'] = BooleanOptionalAction

        cli_meta: CliOpt = try_next(i for i in fld.metadata if isinstance(i, CliOpt)) \
            or CliOpt([f'--{name.replace('_', '-')}'], kwargs)

        parser.add_argument(*cli_meta.names, **kwargs | cli_meta.kwargs)

    return parser

@logger.catch(onerror=lambda _: sys.exit(1))
def main() -> int:  # noqa: D103
    setup_logger('ERROR')

    main_parser = ArgumentParser()

    main_parser.add_argument('--version', '-V', action='store_true',
        help='Shows the installed version and exits.')
    main_parser.add_argument('--log-level', '-l', type=lambda s: s.upper(), choices=[i.name for i in LogLevel],
        default='INFO',
        help='The logging level for this session. "DEBUG" shows more output and can be useful for diagnosing issues.'
            + ' "TRACE" is the most verbose setting and may result in a very large volume of logs, only use this if'
            + ' "DEBUG" hasn\'t helped enough. Log files always use level DEBUG, or TRACE if it is specified.')
    main_parser.add_argument('--no-logfile', dest='log_to_file', action='store_false',
        help='Disables file logging; logs will only be sent to stdout. A log file may still be created if any errors'
            + ' occur before arguments can be parsed.')
    main_parser.add_argument('--yes', '-y', action='store_true',
        help='Skips confirmation prompts.')

    subparsers = main_parser.add_subparsers(dest='action', required=False)

    parser_render = subparsers.add_parser('render')

    # Dynamically add render options as CLI options
    add_args_from_render_opt(parser_render)

    render_subparsers = parser_render.add_subparsers(dest='render_type', required=True)

    for k, v in render_arg_parsers.items():
        render_subparsers.add_parser(k, parents=[v])

    # Parse args
    args = main_parser.parse_args()

    if args.version:
        console.print(__version__)

        return 0

    log_level = LogLevel[args.log_level]
    log_to_file: bool = args.log_to_file

    # Start logging
    _, file_log = setup_logger(
        log_level,
        min(log_level, LogLevel.DEBUG),
        logs_dir=DEFAULT_LOGS_DIR if log_to_file else None,
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
    if file_log:
        logger.debug(f'log directory: {file_log[1]}')

    match args.action:
        case 'render':
            render_json: Path | None = args.render_json

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
