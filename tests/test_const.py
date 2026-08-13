from positionpolling.const import PACKAGE_ROOT


def test_package_name() -> None:
    assert PACKAGE_ROOT.name == 'positionpolling'
