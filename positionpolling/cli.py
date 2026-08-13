"""Command-line interface for positionpolling."""
import sys
from argparse import ArgumentParser, BooleanOptionalAction
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from loguru import logger
from pydantic.fields import FieldInfo

from positionpolling import __version__
from positionpolling.const import PACKAGE_ROOT, LogLevel, console, setup_logger
from positionpolling.models import RENDER_OPT_DEFAULT, RenderOpt

parser_render_trail = ArgumentParser(add_help=False)
parser_render_trail.add_argument('source', type=str,
    help='Path or URL to the SQL database to use.')
parser_render_trail.add_argument('--out', '-o', type=Path, required=True,
    help='Where to save the rendered video.')
parser_render_trail.add_argument('--time-factor', '-t', type=float)

render_arg_parsers: dict[str, ArgumentParser] = {
    'trail': parser_render_trail,
}

@logger.catch()
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

    # Dynamically add render options as CLI options
    for name, fld in cast('dict[str, FieldInfo]', RenderOpt.model_fields).items():
        kwargs: dict[str, Any] = {'help': fld.description}

        if fld.annotation is bool:
            kwargs['action'] = BooleanOptionalAction

        parser.add_argument(f'--{name.replace('_', '-')}', **kwargs)

    subparsers = parser.add_subparsers(dest='action', required=False)

    parser_render = subparsers.add_parser('render')
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

            console.print(render_opt.display())

            render_type: str = args.render_type
            render_modpath: str = f'{PACKAGE_ROOT.name}.{render_type}'
            logger.debug(f'Importing render module for "{render_type}" using path {render_modpath}')
            render_module = import_module(render_modpath)

            return render_module.cli(render_opt, args)
        case _:
            raise ValueError(f'Invalid action: {args.action!r}')

if __name__ == '__main__':
    sys.exit(main())
