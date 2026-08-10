"""Command-line interface for positionpolling."""
import sys

from positionpolling import __version__
from positionpolling.const import console


def main() -> int:  # noqa: D103
    console.print(__version__)

    return 0

if __name__ == '__main__':
    sys.exit(main())
