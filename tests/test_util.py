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
