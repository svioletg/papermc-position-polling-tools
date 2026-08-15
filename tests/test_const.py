import pytest

from positionpolling import const
from positionpolling.const import PACKAGE_ROOT
from positionpolling.errors import ValueWarning


@pytest.mark.parametrize(('value', 'expected'),
    [
        ('1', True),
        ('true', True),
        ('True', True),
        ('TRUE', True),
        ('tRuE', True),

        ('0', False),
        ('false', False),
        ('False', False),
        ('FALSE', False),
        ('fAlSe', False),
    ],
)
def test_get_env_bool(value: str, expected: bool) -> None:
    assert const.get_env_bool('VAR', env={'VAR': value}) is expected

def test_get_env_bool_invalid() -> None:
    with pytest.warns(
            ValueWarning,
            match=r'Boolean environment variable expected to be any of 1/true/0/false; defaulting to false',
        ):
        const.get_env_bool('VAR', strict=False, env={'VAR': '2'})

    with pytest.raises(ValueError, match=r'Boolean environment variable must be any of 1/true/0/false'):
        const.get_env_bool('VAR', strict=True, env={'VAR': '2'})

def test_package_name() -> None:
    assert PACKAGE_ROOT.name == 'positionpolling'
