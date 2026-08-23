from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from geometry import Tuple4
from loguru import logger

from positionpolling import util
from positionpolling.const import LogLevel, setup_logger
from tests import TESTS_DATA_TMP_DIR, gen_pos_logs


def test_ask_overwrite() -> None:
    mock_input = Mock(input)

    path: Path = TESTS_DATA_TMP_DIR / 'file.txt'
    assert util.ask_overwrite(path) is True

    path.touch()

    with patch('builtins.input', mock_input):
        mock_input.return_value = 'y'
        assert util.ask_overwrite(path) is True
        assert mock_input.call_count == 1

        mock_input.return_value = 'n'
        assert util.ask_overwrite(path) is False
        assert mock_input.call_count == 2  # noqa: PLR2004

def test_assert_all() -> None:
    util.assert_all((1, 'true', True, [1]))

    with pytest.raises(AssertionError, match=r"predicate \(''\) is False"):
        util.assert_all((1, '', False, []))

def test_assert_true() -> None:
    util.assert_true(True)  # noqa: FBT003
    util.assert_true(1)
    util.assert_true('true')

    with pytest.raises(AssertionError):
        util.assert_true(False)  # noqa: FBT003

    with pytest.raises(AssertionError):
        util.assert_true(0)

    with pytest.raises(AssertionError):
        util.assert_true('')

@pytest.mark.parametrize(('a', 'b', 'delta', 'expected'),
    [
        ((255, 0, 0, 255), (  0, 255,   0, 255), 25, (191,  63,   0, 255)),
        ((127, 0, 0, 255), (  0, 255,   0, 255), 25, ( 95,  63,   0, 255)),
        ((  0, 0, 0, 255), (  0, 255,   0, 255), 25, (  0,  63,   0, 255)),
        ((255, 0, 0, 255), (  0, 255,   0, 255), 50, (127, 127,   0, 255)),
        ((127, 0, 0, 255), (  0, 255,   0, 255), 50, ( 63, 127,   0, 255)),
        ((  0, 0, 0, 255), (  0, 255,   0, 255), 50, (  0, 127,   0, 255)),
        ((255, 0, 0, 255), (  0, 255,   0, 255), 75, ( 63, 191,   0, 255)),
        ((127, 0, 0, 255), (  0, 255,   0, 255), 75, ( 31, 191,   0, 255)),
        ((  0, 0, 0, 255), (  0, 255,   0, 255), 75, (  0, 191,   0, 255)),
    ],
)
def test_blend_color(a: Tuple4[int], b: Tuple4[int], delta: float, expected: Tuple4[float]) -> None:
    assert util.blend_color(a, b, delta) == expected
    assert util.blend_color(a, b, 0) == a
    assert util.blend_color(a, b, 100) == b

@pytest.mark.parametrize(('obj', 'typ', 'fn', 'expected'),
    [
        (0, int, None, 0),
        ('0', int, None, 0),
        ('2023-08-31', datetime, datetime.fromisoformat, datetime(2023, 8, 31)),  # noqa: DTZ001
    ],
)
def test_coerce[T](obj: object, typ: type[T], fn: Callable[[object], T] | None, expected: T) -> None:
    value = util.coerce(obj, typ, fn)
    assert isinstance(value, expected.__class__)
    assert value == expected

@pytest.mark.parametrize(('value', 'r_from', 'r_to', 'expected'),
    [
        (-25, (0, 100), (0, 50), -12.5),
        (0, (0, 100), (0, 50), 0),
        (25, (0, 100), (0, 50), 12.5),
        (50, (0, 100), (0, 50), 25),
        (75, (0, 100), (0, 50), 37.5),
        (100, (0, 100), (0, 50), 50),
        (125, (0, 100), (0, 50), 62.5),

        (-25, (0, 100), (10, 20), 7.5),
        (0, (0, 100), (10, 20), 10),
        (25, (0, 100), (10, 20), 12.5),
        (50, (0, 100), (10, 20), 15),
        (75, (0, 100), (10, 20), 17.5),
        (100, (0, 100), (10, 20), 20),
        (125, (0, 100), (10, 20), 22.5),
    ],
)
def test_convert_range(value: float, r_from: tuple[float, float], r_to: tuple[float, float], expected: float) -> None:
    assert util.convert_range(value, r_from, r_to) == expected

def test_gradient() -> None:
    c1 = (255,   0,   0, 255)
    c2 = (  0,   0, 255, 255)
    assert util.gradient(c1, c2, 10) == [util.blend_color(c1, c2, (n / (10 - 1)) * 100) for n in range(10)]
    assert util.gradient(c1, c2, 5) == [util.blend_color(c1, c2, (n / (5 - 1)) * 100) for n in range(5)]
    assert util.gradient(c1, c2, 2) == [util.blend_color(c1, c2, (n / (2 - 1)) * 100) for n in range(2)]

    with pytest.raises(ValueError, match=r"gradient\(\) parameter 'steps' must be >=2: 1"):
        util.gradient(c1, c2, 1)

def test_grid_from_entries() -> None:
    entries = gen_pos_logs(100)

    g = util.grid_from_entries(entries)
    assert g.x1 == min(e.x for e in entries)
    assert g.y1 == min(e.z for e in entries)
    assert g.x2 == max(e.x for e in entries)
    assert g.y2 == max(e.z for e in entries)

    g = util.grid_from_entries(entries, step=(512, 512), origin=(0, 0))
    assert g.step == (512, 512)
    assert g.origin == (0, 0)

def test_group_by() -> None:
    items = [
        {'title': 'Talking Book', 'artist': 'Stevie Wonder'},
        {'title': 'Heroes', 'artist': 'David Bowie'},
        {'title': 'Innervisions', 'artist': 'Stevie Wonder'},
    ]

    by_artist = util.group_by(items, 'artist')
    assert by_artist == {
        'Stevie Wonder': [
            {'title': 'Talking Book', 'artist': 'Stevie Wonder'},
            {'title': 'Innervisions', 'artist': 'Stevie Wonder'},
        ],
        'David Bowie': [
            {'title': 'Heroes', 'artist': 'David Bowie'},
        ],
    }

def test_group_by_attr() -> None:
    entries = gen_pos_logs(10)
    assert all(all(i.player_uuid == k for i in v) for k, v in util.group_by_attr(entries, 'player_uuid').items())
    assert all(all(i.world == k for i in v) for k, v in util.group_by_attr(entries, 'world').items())

@pytest.mark.parametrize('pct_digits', [0, 1, 2, 3, 4])
@pytest.mark.parametrize('level', [i.name for i in LogLevel])
def test_log_progress(monkeypatch: pytest.MonkeyPatch, pct_digits: int, level: str) -> None:
    logs: list[tuple[str, str]] = []

    class MockLoggerOpt:
        def __init__(self, depth: int) -> None:
            assert depth == 1

        def log(self, level: str, msg: str) -> None:
            logs.append((level, msg))

    monkeypatch.setattr(logger, 'opt', MockLoggerOpt)

    for n in range(101):
        util.log_progress(n, 100, pct_digits=pct_digits, level=level)

    # Assert that the right level was used
    assert all(lev == level for lev, _ in logs)
    # Assert that every log is the same width
    assert len({len(s[1]) for s in logs}) == 1

def test_log_progress_show_count(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logger('INFO', logs_dir=None, no_color=True, wrap_stdout=False)

    util.log_progress(25, 100, show_count=True)
    captured = capsys.readouterr()
    assert '( 25/100)' in captured.out.splitlines()[0], repr(captured.out)

    util.log_progress(25, 100, show_count=False)
    captured = capsys.readouterr()
    assert '( 25/100)' not in captured.out.splitlines()[0], repr(captured.out)

@pytest.mark.parametrize(('hexcolor', 'expected'),
    [
        ('ff0000ff', (255, 0, 0, 255)),
        ('ff0000aa', (255, 0, 0, 170)),
        ('ff0000', (255, 0, 0, 255)),
        ('0af', (0, 170, 255, 255)),
        ('0afa', (0, 170, 255, 170)),
    ],
)
def test_rgba(hexcolor: str, expected: Tuple4[int]) -> None:
    assert util.rgba(hexcolor) == expected

def test_time_this() -> None:
    times: list[float] = []
    value: int = 0

    for _ in range(100):
        with util.time_this(times):
            value += 1

    assert len(times) == 100  # noqa: PLR2004
    assert value == 100  # noqa: PLR2004

def test_try_next() -> None:
    assert util.try_next(i * 2 for i in range(5, 10)) == 10  # noqa: PLR2004
    assert util.try_next(i * 2 for i in range(5, 10) if i < 5) is None  # noqa: PLR2004
    assert util.try_next((i * 2 for i in range(5, 10)), -1) == 10  # noqa: PLR2004
    assert util.try_next((i * 2 for i in range(5, 10) if i < 5), -1) == -1  # noqa: PLR2004
