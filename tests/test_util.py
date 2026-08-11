from collections.abc import Callable
from datetime import datetime

import pytest
from geometry import Tuple4

from positionpolling import util


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
