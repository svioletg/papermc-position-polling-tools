from argparse import Action, ArgumentParser, BooleanOptionalAction
from typing import Annotated
from unittest.mock import patch

from pydantic import BaseModel

from positionpolling import cli
from positionpolling.models import CliOpt


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
