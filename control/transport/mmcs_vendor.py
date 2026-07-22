"""Lifecycle and exception boundary around the vendored MMCS driver."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from typing import Any

from control.core.exceptions import (
    ConnectionError,
    InstrumentCommandError,
    TransportTimeoutError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def _default_backend_factory(boxes: Mapping[str, str]) -> Any:
    from MMCSDriver.mmcs_driver import MmcsDriver

    return MmcsDriver(box_ip_dict=dict(boxes))


class MmcsVendorTransport:
    """Own one vendor driver instance and its shared UDP resources."""

    def __init__(
        self,
        boxes: Mapping[str, str],
        *,
        backend_factory: Callable[[Mapping[str, str]], Any] | None = None,
    ) -> None:
        if not boxes or not all(isinstance(k, str) and isinstance(v, str) for k, v in boxes.items()):
            raise ValueError("boxes must be a non-empty mapping of names to IP addresses")
        self.boxes = dict(boxes)
        self._backend_factory = backend_factory or _default_backend_factory
        self._backend: Any | None = None
        self._lock = threading.RLock()
        self._generation = 0

    @property
    def is_open(self) -> bool:
        return self._backend is not None

    @property
    def generation(self) -> int:
        return self._generation

    def open(self) -> None:
        with self._lock:
            if self.is_open:
                return
            try:
                self._backend = self._backend_factory(self.boxes)
            except Exception as exc:
                self._backend = None
                raise ConnectionError(f"Failed to connect to MMCS boxes {self.boxes!r}") from exc
            self._generation += 1

    def close(self) -> None:
        with self._lock:
            backend = self._backend
            if backend is None:
                return
            try:
                backend.sys_close()
            except Exception as exc:
                raise ConnectionError("Failed to close MMCS vendor transport") from exc
            self._backend = None

    def call(self, method_name: str, /, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if self._backend is None:
                raise ConnectionError("MMCS transport is not open")
            try:
                method = getattr(self._backend, method_name)
                return method(*args, **kwargs)
            except TimeoutError as exc:
                raise TransportTimeoutError(f"MMCS operation {method_name} timed out") from exc
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"MMCS rejected arguments for {method_name}: {exc}") from exc
            except RuntimeError as exc:
                raise InstrumentCommandError(f"MMCS operation {method_name} failed: {exc}") from exc
            except AttributeError as exc:
                raise InstrumentCommandError(
                    f"MMCS vendor backend does not provide {method_name}"
                ) from exc
            except Exception as exc:
                raise ConnectionError(f"MMCS communication failed during {method_name}") from exc

    def __enter__(self) -> "MmcsVendorTransport":
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except Exception as close_exc:
            if exc_value is not None:
                exc_value.add_note(f"Closing MMCS transport also failed: {close_exc}")
            else:
                raise
