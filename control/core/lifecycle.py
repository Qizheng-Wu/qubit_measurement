"""Common lifecycle contracts."""

from enum import Enum, auto
from typing import Protocol, Self, runtime_checkable

from .identity import InstrumentIdentity


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTED = auto()
    CLOSED = auto()


@runtime_checkable
class InstrumentLifecycle(Protocol):
    @property
    def is_connected(self) -> bool: ...

    def connect(self) -> None: ...

    def identify(self) -> InstrumentIdentity: ...

    def safe_shutdown(self) -> None: ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
