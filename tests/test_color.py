from copy import copy

import pytest

from positionpolling.util import Color


@pytest.mark.parametrize(('source', 'expected'),
    [
        (0xffffffff, 0xffffffff),
        ('#ffffffff', 0xffffffff),
        ((255, 255, 255, 255), 0xffffffff),
        ('white', 0xffffffff),
        ('#ffffff', 0xffffffff),
        ((255, 255, 255), 0xffffffff),
        ('#ffffff00', 0xffffff00),
        ((255, 255, 255, 0), 0xffffff00),
        ('#ffff0000', 0xffff0000),
        ((255, 255, 0, 0), 0xffff0000),
        ('#ffff00', 0xffff00ff),
        ((255, 255, 0), 0xffff00ff),
        ('#ff000000', 0xff000000),
        ((255, 0, 0, 0), 0xff000000),
        ('#ff0000', 0xff0000ff),
        ((255, 0, 0), 0xff0000ff),
        ('#00000000', 0),
        ((0, 0, 0, 0), 0),
        ('#000000ff', 0x000000ff),
        ((0, 0, 0), 0x000000ff),
        ('black', 0x000000ff),
        ('black#00', 0),
    ],
)
def test_color_init(source: int | str | tuple[int, int, int] | tuple[int, int, int, int], expected: int) -> None:
    assert Color(expected).value == expected
    assert Color(source).value == expected

@pytest.mark.parametrize('r', [0, 255])
@pytest.mark.parametrize('g', [0, 255])
@pytest.mark.parametrize('b', [0, 255])
@pytest.mark.parametrize('a', [0, 255])
def test_color_props_rgba(r: int, g: int, b: int, a: int) -> None:
    source = (r, g, b, a)

    color = Color(source)
    assert (color.r, color.g, color.b, color.a) == color.rgba() == source
    assert color.rgb() == source[:3]

def test_color_repr() -> None:
    assert repr(Color((0,64, 127, 255))) == 'Color(value=4227071)'

def test_color_copy() -> None:
    color = Color(0xaabbccdd)
    new_color = copy(color)
    assert color is not new_color
    assert color.value == new_color.value == 0xaabbccdd  # noqa: PLR2004

def test_color_eq() -> None:
    assert Color(0xaabbccdd) == Color(0xaabbccdd)
    assert Color(0xaabbccdd) == 0xaabbccdd  # noqa: PLR2004
    assert Color(0xaabbccdd) != 0xaabbcc  # noqa: PLR2004

def test_color_hash() -> None:
    assert hash(Color(0xaabbccdd)) == hash(Color(0xaabbccdd))
    assert {Color(0xaabbccdd): 1}[Color(0xaabbccdd)] == 1

def test_color_iter() -> None:
    assert tuple(Color((0, 64, 127, 255))) == (0, 64, 127, 255)

def test_color_getitem() -> None:
    color = Color((0, 64, 127, 255))
    assert color[0] == 0 == color.r
    assert color[1] == 64 == color.g  # noqa: PLR2004
    assert color[2] == 127 == color.b  # noqa: PLR2004
    assert color[3] == 255 == color.a  # noqa: PLR2004

    with pytest.raises(ValueError, match=r'index must be between 0 and 3'):
        color[-1]
    with pytest.raises(ValueError, match=r'index must be between 0 and 3'):
        color[4]

def test_color_hex() -> None:
    color = Color((0, 64, 127, 255))
    assert color.hex() == '0x00407fff'
    assert color.hex('#') == '#00407fff'
    assert color.hex('') == '00407fff'
    assert color.hex(alpha=False) == '0x00407f'
    assert color.hex('#', alpha=False) == '#00407f'
    assert color.hex('', alpha=False) == '00407f'

def test_color_name() -> None:
    assert Color('red').name() == 'red'
    assert Color('red#7f').name() == 'red'
    assert Color(0xaabbccdd).name() is None

def test_color_set_value() -> None:
    color = Color(0)
    color.value = 1
    assert color.value == 1

    with pytest.raises(TypeError):
        color.value = '#ffffff'  # ty: ignore[invalid-assignment]

    with pytest.raises(ValueError, match=r'cannot be negative'):
        color.value = -1

    with pytest.raises(ValueError, match=r'cannot be larger than'):
        color.value = 0x100000000
