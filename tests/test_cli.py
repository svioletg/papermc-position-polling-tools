from argparse import Action, ArgumentParser, BooleanOptionalAction
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from positionpolling import cli
from positionpolling.const import DEFAULT_LOGS_DIR
from positionpolling.models import CliOpt

PLAYERS: list[str] = [str(uuid4()) for _ in range(10)]

def test_add_args_from_render_opt() -> None:
    class MockRenderOpt(BaseModel):
        number: int = 0
        flag: bool = False
        favorite_color: Annotated[str, CliOpt(['--color', '-c'])] = 'purple'
        number_list: list[float] = []

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
    assert opt_number_list.type is cli.comma_split

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
