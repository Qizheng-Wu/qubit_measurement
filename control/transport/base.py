"""Transport contracts."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    @property
    def is_open(self) -> bool: ...

    def open(self) -> None: ...

    def close(self) -> None: ...
