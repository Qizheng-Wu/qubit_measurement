"""Thread-safe PyVISA transport with project-owned errors."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Iterator

import numpy as np
import pyvisa
from pyvisa.errors import VisaIOError

from control.core.exceptions import ConnectionError, ProtocolError, TransportTimeoutError

logger = logging.getLogger(__name__)


class VisaTransport:
    def __init__(
        self,
        resource_name: str,
        *,
        timeout_s: float,
        read_termination: str | None,
        write_termination: str | None,
        resource_manager_factory: Callable[[], Any] | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.resource_name = resource_name
        self.timeout_s = float(timeout_s)
        self.read_termination = read_termination
        self.write_termination = write_termination
        self._rm_factory = resource_manager_factory or pyvisa.ResourceManager
        self._resource_manager: Any | None = None
        self._resource: Any | None = None
        self._lock = threading.RLock()

    @property
    def is_open(self) -> bool:
        return self._resource is not None

    def open(self) -> None:
        with self._lock:
            if self.is_open:
                return
            rm = None
            try:
                rm = self._rm_factory()
                resource = rm.open_resource(
                    self.resource_name,
                    read_termination=self.read_termination,
                    write_termination=self.write_termination,
                )
                resource.timeout = int(self.timeout_s * 1000)
            except Exception as exc:
                if rm is not None:
                    try:
                        rm.close()
                    except Exception:
                        logger.debug("Failed to close VISA manager after open error", exc_info=True)
                raise ConnectionError(
                    f"Failed to open VISA resource {self.resource_name!r}"
                ) from exc
            self._resource_manager = rm
            self._resource = resource

    def close(self) -> None:
        with self._lock:
            resource, rm = self._resource, self._resource_manager
            self._resource = None
            self._resource_manager = None
            errors: list[Exception] = []
            for obj in (resource, rm):
                if obj is not None:
                    try:
                        obj.close()
                    except Exception as exc:
                        errors.append(exc)
            if errors:
                raise ConnectionError(
                    f"Failed to close VISA resource {self.resource_name!r}"
                ) from errors[0]

    def _require_resource(self) -> Any:
        if self._resource is None:
            raise ConnectionError(f"VISA resource {self.resource_name!r} is not open")
        return self._resource

    def _translate_error(self, operation: str, exc: Exception) -> Exception:
        if isinstance(exc, VisaIOError) and exc.error_code == pyvisa.constants.StatusCode.error_timeout:
            return TransportTimeoutError(
                f"VISA {operation} timed out for {self.resource_name!r}"
            )
        return ConnectionError(f"VISA {operation} failed for {self.resource_name!r}")

    def write(self, command: str) -> None:
        with self._lock:
            resource = self._require_resource()
            started = time.perf_counter()
            try:
                resource.write(command)
            except Exception as exc:
                raise self._translate_error("write", exc) from exc
            logger.debug("VISA write %.3fs: %s", time.perf_counter() - started, command)

    def query(self, command: str) -> str:
        with self._lock:
            resource = self._require_resource()
            started = time.perf_counter()
            try:
                response = resource.query(command)
            except Exception as exc:
                raise self._translate_error("query", exc) from exc
            logger.debug("VISA query %.3fs: %s", time.perf_counter() - started, command)
            return str(response).strip()

    def query_float(self, command: str) -> float:
        response = self.query(command)
        try:
            return float(response)
        except ValueError as exc:
            raise ProtocolError(f"Expected float response to {command!r}, got {response!r}") from exc

    def query_int(self, command: str) -> int:
        response = self.query(command)
        try:
            return int(float(response))
        except ValueError as exc:
            raise ProtocolError(f"Expected integer response to {command!r}, got {response!r}") from exc

    def query_binary(
        self,
        command: str,
        *,
        datatype: str,
        is_big_endian: bool,
    ) -> np.ndarray:
        with self._lock:
            resource = self._require_resource()
            started = time.perf_counter()
            try:
                result = resource.query_binary_values(
                    command,
                    datatype=datatype,
                    is_big_endian=is_big_endian,
                    container=np.array,
                )
            except Exception as exc:
                raise self._translate_error("binary query", exc) from exc
            array = np.asarray(result)
            logger.debug(
                "VISA binary query %.3fs: %s (%d values)",
                time.perf_counter() - started,
                command,
                array.size,
            )
            return array

    @contextmanager
    def temporary_timeout(self, timeout_s: float) -> Iterator[None]:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        with self._lock:
            resource = self._require_resource()
            previous = resource.timeout
            resource.timeout = int(timeout_s * 1000)
            try:
                yield
            finally:
                resource.timeout = previous

    def __enter__(self) -> "VisaTransport":
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except Exception as close_exc:
            if exc_value is not None:
                exc_value.add_note(f"Closing VISA transport also failed: {close_exc}")
            else:
                raise
