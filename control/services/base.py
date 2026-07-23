"""Shared connection and active-run lifecycle for instrument services."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Self

from control.core.exceptions import InstrumentStateError


class BaseInstrumentService:
    """Own a driver while exposing explicit connection and run scopes."""

    def __init__(self, driver: Any) -> None:
        self._driver = driver
        self._connected = False
        self._active_run: object | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._driver.is_connected

    @contextmanager
    def connected(self) -> Iterator[Self]:
        if self._connected:
            raise InstrumentStateError("Instrument service is already connected")
        with self._driver:
            self._connected = True
            try:
                yield self
            finally:
                self._connected = False
                self._active_run = None

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise InstrumentStateError(
                "Instrument service must be used inside connected()"
            )

    def _activate_run(self, run: object) -> None:
        self._require_connected()
        if self._active_run is not None:
            raise InstrumentStateError("Instrument service is already running")
        self._active_run = run

    def _require_active_run(self, run: object) -> None:
        self._require_connected()
        if self._active_run is not run:
            raise InstrumentStateError("Run handle is no longer active")

    def _deactivate_run(self, run: object) -> None:
        if self._active_run is run:
            self._active_run = None
