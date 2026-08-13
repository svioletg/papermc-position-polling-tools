"""Command-line interface for positionpolling."""
import sys
from argparse import ArgumentParser, BooleanOptionalAction
from importlib import import_module
from pathlib import Path
from typing import Any, Never, cast

from loguru import logger
from pydantic.fields import FieldInfo

from positionpolling import __version__
from positionpolling.const import PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, CliOpt, RenderOpt
from positionpolling.util import try_next

parser_render_trail = ArgumentParser(add_help=False)
parser_render_trail.add_argument('source', type=str,
    help='Path or URL to the SQL database to use.')
parser_render_trail.add_argument('--out', '-o', type=Path, required=True,
    help='Where to save the rendered video.')

render_arg_parsers: dict[str, ArgumentParser] = {
    'trail': parser_render_trail,
}

def abort(err: str | Exception, *, log: bool = False, status: int = 1) -> Never:
    """Print an error message or exception without a full traceback and exit with code ``status``.

    :param log: If ``False``, the message is printed using the ``rich`` console with ``[err]...[/]`` markup. If
        ``True``, the message is logged with ``logger.error()``.
    """
    msg = err if isinstance(err, str) else f'{err.__class__.__name__}: {err}'

    if log:
        logger.error(msg)
    else:
        console.print(f'[err]{msg}[/]')

    sys.exit(status)

def add_args_from_render_opt(parser: ArgumentParser) -> ArgumentParser:
    """Adds arguments to an ``ArgumentParser`` object from the fields in :class:`models.RenderOpt`.

    Returns the passed parser.
    """
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

    parser = ArgumentParser()

    parser.add_argument('--version', '-V', action='store_true',
        help='Shows the installed version and exits.')
    parser.add_argument('--log-level', '-l', type=lambda s: s.upper(), choices=[i.name for i in LogLevel],
        default='INFO',
        help='The logging level for this session.')
    parser.add_argument('--render-json', '-j', type=Path, metavar='PATH',
        help='Path to a JSON file defining render options to use.')
    parser.add_argument('--yes', '-y', action='store_true',
        help='Skips confirmation prompts.')


    subparsers = parser.add_subparsers(dest='action', required=False)

    parser_render = subparsers.add_parser('render')

    # Dynamically add render options as CLI options
    add_args_from_render_opt(parser_render)

    render_subparsers = parser_render.add_subparsers(dest='render_type', required=True)

    for k, v in render_arg_parsers.items():
        render_subparsers.add_parser(k, parents=[v])

    # Parse args
    args = parser.parse_args()
    setup_logger(LogLevel[args.log_level])
    if args.version:
        console.print(__version__)

        return 0
    elif not args.action:
        parser.print_help()

        return 0

    match args.action:
        case 'render':
            render_json: Path | None = args.render_json

            logger.trace('Getting render options...')
            logger.trace(f'RenderOpt JSON file: {render_json or '<none>'}')

            render_opt: RenderOpt = (RenderOpt.from_json(render_json) if render_json else RENDER_OPT_DEFAULT).replace(
                {k:v for k, v in args.__dict__.items() if v is not None},
            )

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
