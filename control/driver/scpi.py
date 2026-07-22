"""Shared SCPI driver lifecycle."""

from __future__ import annotations

import logging
from typing import Self

from control.core.exceptions import ConnectionError, InstrumentCommandError
from control.core.identity import InstrumentIdentity
from control.transport.visa import VisaTransport

logger = logging.getLogger(__name__)


class ScpiInstrumentDriver:
    def __init__(self, transport: VisaTransport) -> None:
        self.transport = transport
        self._connected = False
        self._identity: InstrumentIdentity | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self.transport.is_open

    def connect(self) -> None:
        if self.is_connected:
            return
        self.transport.open()
        try:
            self._identity = self.identify()
        except BaseException as exc:
            try:
                self.transport.close()
            except Exception as cleanup_exc:
                exc.add_note(f"Closing transport after failed identification also failed: {cleanup_exc}")
            self._connected = False
            raise
        self._connected = True

    def identify(self) -> InstrumentIdentity:
        return InstrumentIdentity.parse(self.transport.query("*IDN?"))

    @property
    def identity(self) -> InstrumentIdentity:
        if self._identity is None:
            raise ConnectionError("Instrument identity is unavailable before connect()")
        return self._identity

    def reset(self) -> None:
        self.transport.write("*RST")

    def wait_operation_complete(self, timeout_s: float) -> None:
        with self.transport.temporary_timeout(timeout_s):
            response = self.transport.query("*OPC?")
        if response not in {"1", "+1"}:
            raise InstrumentCommandError(f"Unexpected *OPC? response: {response!r}")

    def check_error(self) -> None:
        response = self.transport.query("SYST:ERR?")
        code = response.split(",", 1)[0].strip()
        if code not in {"0", "+0"}:
            raise InstrumentCommandError(response)

    def safe_shutdown(self) -> None:
        """Put the instrument in a safe state. Subclasses should override."""

    def close(self) -> None:
        if not self.transport.is_open:
            self._connected = False
            return
        try:
            self.safe_shutdown()
        except Exception:
            logger.warning("Instrument safe shutdown failed", exc_info=True)
        finally:
            self.transport.close()
            self._connected = False

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except Exception as close_exc:
            if exc_value is not None:
                exc_value.add_note(f"Closing SCPI instrument also failed: {close_exc}")
            else:
                raise
