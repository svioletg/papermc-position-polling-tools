import shutil

import pytest

from tests import TESTS_DATA_TMP_DIR


def pytest_sessionstart(session: pytest.Session) -> None:  # noqa: ARG001
    # Clear tests/data/tmp
    if TESTS_DATA_TMP_DIR.exists():
        shutil.rmtree(TESTS_DATA_TMP_DIR)

    TESTS_DATA_TMP_DIR.mkdir()
