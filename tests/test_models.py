import json
from itertools import chain
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError, ValidationInfo

from positionpolling import models
from positionpolling.const import World
from tests import TESTS_DATA_TMP_DIR, gen_pos_logs, tempdb

if TYPE_CHECKING:
    from positionpolling.models import ValidatorFunc

CREATE_PLAYER_POSITIONS_TABLE_STMT: str = 'CREATE TABLE player_positions(' \
    + 'timestamp REAL,' \
    + 'player_uuid TEXT,' \
    + 'world TEXT,' \
    + 'x REAL,' \
    + 'y REAL,' \
    + 'z REAL)'

def test_vld_none_ok() -> None:
    mock = Mock()

    def vld_positive(value: object, _info: ValidationInfo) -> int:
        if not isinstance(value, int):
            raise TypeError(f"Expected type 'int', got: {value!r}")

        if value < 0:
            raise ValueError(f'Value must be positive: {value!r}')

        return value

    fn: ValidatorFunc[int | None] = models.vld_nullable(vld_positive)

    assert fn(1, mock) == 1
    assert fn(None, mock) is None
    with pytest.raises(ValueError, match=r'Value must be positive'):
        fn(-1, mock)

def test_vld_range() -> None:
    mock = Mock()

    validate = models.vld_range(0, 100)
    validate_clamp = models.vld_range(0, 100, 'clamp')
    for n in range(-50, 150, 10):
        if 0 <= n <= 100:  # noqa: PLR2004
            assert validate(n, mock) == validate_clamp(n, mock)
        else:
            with pytest.raises(ValueError, match='Value must be >=0 and <=100:'):
                assert validate(n, mock) == min(max(0, n), 100)
            assert validate_clamp(n, mock) == min(max(0, n), 100)

def test_Entry_from_to_row() -> None:
    row: models.EntryRowTuple = (0, str(uuid4()), 'minecraft:overworld', 100, 70, 200)
    entry: models.Entry = models.Entry.from_row(row)

    assert entry.to_row() == row
    assert models.Entry.from_row(entry.to_row()) == entry

def test_Entry_magic_sub() -> None:
    player1 = uuid4()
    player2 = uuid4()

    e1 = models.Entry(1000, player1, World.OVERWORLD, 100, 70, 200)
    e2 = models.Entry(1500, player2, World.NETHER, 200, 60, 150)

    # Subtracting two entries uses the player_uuid and world values for the left operand
    sub = e2 - e1
    assert sub == models.Entry(
        500,
        player2,
        World.NETHER,
        100,
        -10,
        -50,
    )

def test_PlayerPositions_from_sql() -> None:
    entries: tuple[models.Entry, ...] = tuple(gen_pos_logs(10))
    entries_values: list[models.EntryRowTuple] = [e.to_row() for e in entries]

    with tempdb(CREATE_PLAYER_POSITIONS_TABLE_STMT, {'player_positions': entries_values}) as (conn, f):
        conn.close()

        data = models.PlayerPositions.from_sql(f.name)

    assert data.entries == entries

def test_PlayerPositions_by_player() -> None:
    playerlogs: dict[str, list[models.Entry]] = {
        (player1 := str(uuid4())):gen_pos_logs(10, players=[player1]),
        (player2 := str(uuid4())):gen_pos_logs(5, players=[player2]),
        (player3 := str(uuid4())):gen_pos_logs(20, players=[player3]),
    }

    data = models.PlayerPositions(tuple(chain.from_iterable(playerlogs.values())))
    assert len(data.entries) == sum(len(es) for es in playerlogs.values())

    by_player = data.by_player
    for k, v in playerlogs.items():
        assert by_player[k] == v

def test_RenderOpt_ensure_frozen() -> None:
    opt = models.RenderOpt()
    with pytest.raises(ValidationError, match=r'.*Instance is frozen.*'):
        opt.progress_bar = False  # ty: ignore[invalid-assignment]

def test_RenderOpt_json() -> None:
    opt_dict: dict[str, Any] = {
        'progress_bar': True,
        'progress_log_interval': 0.25,
        'world_crop': (-100, -100, 100, 100),
        'v_fix': False,
        'v_fps': 30,
        'v_time_factor': 0.1,
    }

    with NamedTemporaryFile('w', dir=TESTS_DATA_TMP_DIR, delete=True, delete_on_close=False) as f:
        json_path: str = f.name
        json.dump(opt_dict, f)

        f.close()

        opt = models.RenderOpt.from_json(json_path)
        assert opt.model_dump(mode='python') == opt_dict

def test_RenderOpt_changed() -> None:
    opt = models.RenderOpt(progress_bar=True)
    assert opt.changed() == {'progress_bar': True}

def test_RenderOpt_cli_meta() -> None:
    for name in models.RenderOpt.model_fields:
        assert models.RenderOpt.cli_meta().get(name)

def test_RenderOpt_display() -> None:
    opt = models.RenderOpt()
    assert opt.display() == """
Render options:
    progress_bar = False
    progress_log_interval = 0.1
    world_crop = None
    v_fix = True
    v_fps = 60
    v_time_factor = 0.25
""".strip()

    opt = models.RenderOpt(progress_log_interval=0.25, world_crop=(-100, -100, 100, 100))
    assert opt.display() == """
Render options:
    progress_bar = False
    progress_log_interval* = 0.25
    world_crop* = (-100.0, -100.0, 100.0, 100.0)
    v_fix = True
    v_fps = 60
    v_time_factor = 0.25
""".strip()

    opt = models.RenderOpt(progress_log_interval=0.25, world_crop=(-100, -100, 100, 100))
    assert opt.display(mark_changes=False) == """
Render options:
    progress_bar = False
    progress_log_interval = 0.25
    world_crop = (-100.0, -100.0, 100.0, 100.0)
    v_fix = True
    v_fps = 60
    v_time_factor = 0.25
""".strip()

def test_RenderOpt_replace() -> None:
    opt = models.RenderOpt(v_fps=30)
    assert opt.replace(models.RenderOpt(progress_bar=True)) == models.RenderOpt(progress_bar=True, v_fps=30)
    assert opt.replace({'progress_bar': True}) == models.RenderOpt(progress_bar=True, v_fps=30)
    assert opt | {'progress_bar': True} == models.RenderOpt(progress_bar=True, v_fps=30)
