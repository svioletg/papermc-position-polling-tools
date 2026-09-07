from argparse import Action, ArgumentParser, BooleanOptionalAction
from functools import cache
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, ClassVar, TypeAliasType, get_args, get_origin
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from positionpolling import __version__, cli
from positionpolling.const import DEFAULT_LOGS_DIR
from positionpolling.models import CliOpt
from positionpolling.util import comma_split, try_next
from tests import TESTS_DATA_DIR

PLAYERS: list[str] = [str(uuid4()) for _ in range(10)]

def test_add_args_from_render_opt() -> None:
    class MockRenderOpt(BaseModel):
        _cli_meta: ClassVar[dict[str, CliOpt] | None] = None
        number: int = 0
        flag: bool = False
        favorite_color: Annotated[str, CliOpt(['--color', '-c'])] = 'purple'
        number_list: list[float] = []

        @classmethod
        @cache
        def cli_meta(cls) -> dict[str, CliOpt]:
            """Dictionary of field names to their respective :class:`CliOpt` instances."""
            if cls._cli_meta is None:
                cls._cli_meta = {}
                for name, fld in cls.model_fields.items():
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

                    cli_meta: CliOpt | None = try_next(i for i in fld.metadata if isinstance(i, CliOpt))
                    if cli_meta:
                        cli_meta.kwargs = kwargs | cli_meta.kwargs

                    cls._cli_meta[name] = cli_meta or CliOpt([f'--{name.replace('_', '-')}'], kwargs)

            return cls._cli_meta

    parser = ArgumentParser()

    with patch('positionpolling.cli.RenderOpt', MockRenderOpt):
        cli.add_args_from_render_opt(parser)

    action_map: dict[str, Action] = {act.dest:act for act in parser._actions}  # noqa: SLF001

    opt_number = action_map['number']
    assert opt_number.option_strings == ['--number']
    assert opt_number.type is int

    opt_flag = action_map['flag']
    assert opt_flag.option_strings == ['--flag', '--no-flag']
    assert isinstance(opt_flag, BooleanOptionalAction)

    opt_favorite_color = action_map['favorite_color']
    assert opt_favorite_color.option_strings == ['--color', '-c']
    assert opt_favorite_color.type is str

    opt_number_list = action_map['number_list']
    assert opt_number_list.option_strings == ['--number-list']
    assert opt_number_list.type is comma_split

MAIN_PARSER_DEFAULTS: dict[str, Any] = {
    'version': False,
    'log_level': 'INFO',
    'log_file': DEFAULT_LOGS_DIR,
    'no_color': False,
    'yes': False,
}

@pytest.mark.parametrize(('args', 'parsed_expected'),
    [
        ([], {}),
        (['--log-level', 'debug'], {'log_level': 'DEBUG'}),
        (['--logfile', 'mylogs'], {'log_file': Path('mylogs')}),
        (['--no-logfile'], {'log_file': False}),
    ],
)
def test_parse_main(args: list[str], parsed_expected: dict[str, Any]) -> None:
    parsed = cli.main_parser.parse_args(args)
    parsed_expected = MAIN_PARSER_DEFAULTS | parsed_expected

    for name, value in parsed_expected.items():
        assert getattr(parsed, name) == value

RENDER_TRAIL_PARSER_DEFAULTS: dict[str, Any] = {
    'input': ...,
    'out': None,
    'video': None,
    'player': None,
    'desat_per_frame': 0.95,
}

@pytest.mark.parametrize(('args', 'parsed_expected'),
    params := [
        (
            ['--input', 'data.db', '--out', 'trail.png'],
            {
                'input': 'data.db',
                'out': Path('trail.png'),
            },
        ),
        (
            ['--input', 'data.db', '--video', 'trail.mp4'],
            {
                'input': 'data.db',
                'video': Path('trail.mp4'),
            },
        ),
        (
            ['--input', 'data.db', '--out', 'trail.png', '--video', 'trail.mp4'],
            {
                'input': 'data.db',
                'out': Path('trail.png'),
                'video': Path('trail.mp4'),
            },
        ),
        (
            ['--input', 'data.db', '--player', PLAYERS[0]],
            {
                'input': 'data.db',
                'player': [PLAYERS[0]],
            },
        ),
        # Test multiple players given to single option
        (
            ['--input', 'data.db', '--player', *PLAYERS],
            {
                'input': 'data.db',
                'player': PLAYERS,
            },
        ),
        # Test multiple players given as separate options
        (
            ['--input', 'data.db'] + [i for p in PLAYERS for i in ('--player', p)],
            {
                'input': 'data.db',
                'player': PLAYERS,
            },
        ),
    ],
)
def test_parse_render_trail(args: list[str], parsed_expected: dict[str, Any]) -> None:
    parsed = cli.parser_render_trail.parse_args(args)
    parsed_expected = RENDER_TRAIL_PARSER_DEFAULTS | parsed_expected

    for name, value in parsed_expected.items():
        assert getattr(parsed, name) == value

INSPECT_PARSER_DEFAULTS: dict[str, Any] = {
    'source': ...,
    'inspect_out': None,
    'inspect_out_format': cli.InspectFormat.TABLE,
    'inspect_action': ...,
}

@pytest.mark.parametrize(('args', 'parsed_expected'),
    [
        (
            ['--input', 'data.db', 'count'],
            {
                'source': 'data.db',
                'inspect_action': 'count',
            },
        ),
        (
            ['--input', 'data.db', '--out', 'results.txt', 'count'],
            {
                'source': 'data.db',
                'inspect_action': 'count',
                'inspect_out': Path('results.txt'),
            },
        ),
        (
            ['--input', 'data.db', '--format', 'csv', 'count'],
            {
                'source': 'data.db',
                'inspect_action': 'count',
                'inspect_out_format': cli.InspectFormat.CSV,
            },
        ),
        (
            ['--input', 'data.db', '--format', 'json', 'count'],
            {
                'source': 'data.db',
                'inspect_action': 'count',
                'inspect_out_format': cli.InspectFormat.JSON,
            },
        ),
        (
            ['--input', 'data.db', '--format', 'table', 'count'],
            {
                'source': 'data.db',
                'inspect_action': 'count',
                'inspect_out_format': cli.InspectFormat.TABLE,
            },
        ),
    ],
)
def test_parse_inspect(args: list[str], parsed_expected: dict[str, Any]) -> None:
    parsed = cli.parser_inspect.parse_args(args)
    parsed_expected = INSPECT_PARSER_DEFAULTS | parsed_expected

    for name, value in parsed_expected.items():
        assert getattr(parsed, name) == value

INSPECT_COUNT_PARSER_DEFAULTS: dict[str, Any] = {
    'player': None,
    'count_total': True,
    'count_sort': ['entries', 'd'],
}

@pytest.mark.parametrize(('args', 'parsed_expected'),
    [
        ([], {}),
        (
            ['--player', PLAYERS[0]],
            {
                'player': [PLAYERS[0]],
            },
        ),
        # Test multiple players given to single option
        (
            ['--player', *PLAYERS],
            {
                'player': PLAYERS,
            },
        ),
        # Test multiple players given as separate options
        (
            [i for p in PLAYERS for i in ('--player', p)],
            {
                'player': PLAYERS,
            },
        ),
        (['--total'], {'count_total': True}),
        (['--no-total'], {'count_total': False}),
        (['--sort', 'entries'], {'count_sort': ['entries']}),
        (['--sort', 'entries:d'], {'count_sort': ['entries', 'd']}),
        (['--sort', 'player'], {'count_sort': ['player']}),
        (['--sort', 'player:d'], {'count_sort': ['player', 'd']}),
    ],
)
def test_parse_inspect_count(args: list[str], parsed_expected: dict[str, Any]) -> None:
    parsed = cli.parser_inspect_count.parse_args(args)
    parsed_expected = INSPECT_COUNT_PARSER_DEFAULTS | parsed_expected

    for name, value in parsed_expected.items():
        assert getattr(parsed, name) == value

def test_main_show_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['--version']) == 0
    assert capsys.readouterr().out == f'{__version__}\n'

    assert cli.main(['-V']) == 0
    assert capsys.readouterr().out == f'{__version__}\n'

def test_main_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2  # noqa: PLR2004
    assert capsys.readouterr().out.startswith('usage:')

def test_main_missing_action(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['--yes']) == 2  # noqa: PLR2004
    assert capsys.readouterr().out.startswith('Missing an action')

def test_inspect_count_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['-l', 'warning', 'inspect', '-i', str(TESTS_DATA_DIR / 'data.db'), 'count']) == 0
    assert capsys.readouterr().out == (TESTS_DATA_DIR / 'data-count.txt').read_text('utf-8')

def test_inspect_count_csv(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['-l', 'warning', 'inspect', '-i', str(TESTS_DATA_DIR / 'data.db'), '-f', 'csv', 'count']) == 0
    assert capsys.readouterr().out == (TESTS_DATA_DIR / 'data-count.csv').read_text('utf-8')

def test_inspect_count_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['-l', 'warning', 'inspect', '-i', str(TESTS_DATA_DIR / 'data.db'), '-f', 'json', 'count']) == 0
    assert capsys.readouterr().out == (TESTS_DATA_DIR / 'data-count.json').read_text('utf-8')

def test_inspect_count_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['-l', 'warning', 'inspect', '-i', str(TESTS_DATA_DIR / 'data.db'), '-f', 'table', 'count']) == 0
    assert capsys.readouterr().out == (TESTS_DATA_DIR / 'data-count.txt').read_text('utf-8')
