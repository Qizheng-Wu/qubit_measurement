"""Rohde & Schwarz FPL-compatible spectrum-analyzer driver."""

import numpy as np

from control.core.exceptions import ProtocolError, ValidationError
from control.transport.visa import VisaTransport

from .scpi import ScpiInstrumentDriver


class SpectrumAnalyzerDriver(ScpiInstrumentDriver):
    def __init__(self, transport: VisaTransport) -> None:
        super().__init__(transport)

    def set_start_hz(self, value: float) -> None:
        self.transport.write(f"FREQ:STAR {value:.12g} Hz")

    def get_start_hz(self) -> float:
        return self.transport.query_float(":FREQ:STAR?")

    def set_stop_hz(self, value: float) -> None:
        self.transport.write(f"FREQ:STOP {value:.12g} Hz")

    def get_stop_hz(self) -> float:
        return self.transport.query_float(":FREQ:STOP?")

    def set_center_hz(self, value: float) -> None:
        self.transport.write(f"FREQ:CENT {value:.12g} Hz")

    def get_center_hz(self) -> float:
        return self.transport.query_float(":FREQ:CENT?")

    def set_span_hz(self, value: float) -> None:
        self.transport.write(f"FREQ:SPAN {value:.12g} Hz")

    def get_span_hz(self) -> float:
        return self.transport.query_float(":FREQ:SPAN?")

    def set_resolution_bandwidth_hz(self, value: float) -> None:
        if value <= 0:
            raise ValidationError("resolution_bandwidth_hz must be positive")
        self.transport.write(f":BAND {value:.12g}")

    def get_resolution_bandwidth_hz(self) -> float:
        return self.transport.query_float(":BAND?")

    def set_points(self, value: int) -> None:
        if not isinstance(value, int) or value < 2:
            raise ValidationError("Spectrum-analyzer points must be an integer >= 2")
        self.transport.write(f"SWE:POIN {value:d}")

    def get_points(self) -> int:
        return self.transport.query_int(":SWE:POIN?")

    def set_input_attenuation_db(self, value: float) -> None:
        if value < 0:
            raise ValidationError("input_attenuation_db cannot be negative")
        self.transport.write(f":INP:ATT {value:.12g} dB")

    def set_continuous(self, enabled: bool) -> None:
        self.transport.write(f":INIT:CONT {int(enabled)}")

    def trigger(self) -> None:
        self.transport.write(":INIT:IMM")

    def abort(self) -> None:
        self.transport.write(":ABOR")

    def fetch_trace_dbm(self, *, expected_points: int | None = None) -> np.ndarray:
        self.transport.write("FORM:DATA REAL,32")
        trace = np.asarray(
            self.transport.query_binary(
                "TRAC:DATA? TRACE1", datatype="f", is_big_endian=False
            ),
            dtype=float,
        )
        if trace.ndim != 1:
            raise ProtocolError(f"Spectrum analyzer returned a {trace.ndim}-D trace")
        if expected_points is not None and trace.size != expected_points:
            raise ProtocolError(
                f"Spectrum analyzer returned {trace.size} points; expected {expected_points}"
            )
        if not np.all(np.isfinite(trace)):
            raise ProtocolError("Spectrum analyzer returned non-finite trace values")
        return trace

    def safe_shutdown(self) -> None:
        self.abort()
        self.set_continuous(False)
