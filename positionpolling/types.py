"""Type aliases and protocols."""
from typing import Protocol


class SupportsGT[T](Protocol):  # noqa: D101
    def __gt__(self, value: T, /) -> bool:  # noqa: D105
        ...

class SupportsLT[T](Protocol):  # noqa: D101
    def __lt__(self, value: T, /) -> bool:  # noqa: D105
        ...
