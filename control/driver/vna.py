"""SCPI VNA driver compatible with the legacy command set."""

from enum import Enum

import numpy as np

from control.core.exceptions import ProtocolError, ValidationError
from control.transport.visa import VisaTransport

from .scpi import ScpiInstrumentDriver


class VnaSweepMode(str, Enum):
    CONTINUOUS = "continuous"
    HOLD = "hold"


class VnaDriver(ScpiInstrumentDriver):
    def __init__(self, transport: VisaTransport) -> None:
        super().__init__(transport)

    def preset(self) -> None:
        self.transport.write(":SYSTem:PRESet")

    def set_start_hz(self, value: float) -> None:
        self.transport.write(f"SENS:FREQ:STAR {value:.12g}")

    def get_start_hz(self) -> float:
        return self.transport.query_float("SENS:FREQ:STAR?")

    def set_stop_hz(self, value: float) -> None:
        self.transport.write(f"SENS:FREQ:STOP {value:.12g}")

    def get_stop_hz(self) -> float:
        return self.transport.query_float("SENS:FREQ:STOP?")

    def set_center_hz(self, value: float) -> None:
        self.transport.write(f"SENS:FREQ:CENT {value:.12g}")

    def get_center_hz(self) -> float:
        return self.transport.query_float("SENS:FREQ:CENT?")

    def set_span_hz(self, value: float) -> None:
        self.transport.write(f"SENS:FREQ:SPAN {value:.12g}")

    def get_span_hz(self) -> float:
        return self.transport.query_float("SENS:FREQ:SPAN?")

    def set_points(self, value: int) -> None:
        if not isinstance(value, int) or value < 2:
            raise ValidationError("VNA points must be an integer >= 2")
        self.transport.write(f"SENS:SWE:POIN {value:d}")

    def get_points(self) -> int:
        return self.transport.query_int("SENS:SWE:POIN?")

    def set_bandwidth_hz(self, value: float) -> None:
        if not 1 <= value <= 5e6:
            raise ValidationError("VNA bandwidth_hz must be in [1, 5e6]")
        self.transport.write(f"SENS:BAND {value:.12g}")

    def get_bandwidth_hz(self) -> float:
        return self.transport.query_float("SENS:BAND?")

    def set_power_dbm(self, value: float) -> None:
        if not -85 <= value <= 10:
            raise ValidationError("VNA power_dbm must be in [-85, 10]")
        self.transport.write(f"SOUR:POW {value:.12g}")

    def get_power_dbm(self) -> float:
        return self.transport.query_float("SOUR:POW?")

    def set_averages(self, value: int) -> None:
        if value < 1:
            raise ValidationError("VNA averages must be at least 1")
        self.transport.write("SENS:AVER 1")
        self.transport.write(f"SENS:AVER:COUN {value:d}")

    def get_averages(self) -> int:
        return self.transport.query_int("SENS:AVER:COUN?")

    def clear_averages(self) -> None:
        self.transport.write("SENS:AVER:CLE")

    def set_output(self, enabled: bool) -> None:
        self.transport.write(f"OUTP {int(enabled)}")

    def get_output(self) -> bool:
        return self.transport.query("OUTP?").strip().upper() in {"1", "+1", "ON"}

    def set_sweep_mode(self, mode: VnaSweepMode) -> None:
        if mode is VnaSweepMode.CONTINUOUS:
            self.transport.write(":INIT1:CONT ON")
            self.transport.write(":TRIG:SEQ:SOUR INT")
        elif mode is VnaSweepMode.HOLD:
            self.transport.write(":INIT1:CONT OFF")
        else:
            raise ValidationError(f"Unsupported VNA sweep mode: {mode!r}")

    def arm_bus_trigger(self) -> None:
        self.transport.write(":INIT1:CONT OFF")
        self.transport.write(":TRIG:SEQ:SOUR BUS")

    def trigger(self) -> None:
        self.transport.write(":TRIG:SING")

    def abort(self) -> None:
        self.transport.write(":ABORT")

    def fetch_complex_trace(self, *, expected_points: int | None = None) -> np.ndarray:
        self.transport.write("FORMat:DATA REAL")
        raw = self.transport.query_binary(
            "CALC:DATA:SDAT?", datatype="d", is_big_endian=True
        )
        if raw.ndim != 1 or raw.size % 2:
            raise ProtocolError(f"VNA returned {raw.size} scalar values; expected interleaved pairs")
        trace = raw[::2].astype(float) + 1j * raw[1::2].astype(float)
        if expected_points is not None and trace.size != expected_points:
            raise ProtocolError(
                f"VNA returned {trace.size} points; expected {expected_points}"
            )
        if not np.all(np.isfinite(trace)):
            raise ProtocolError("VNA returned non-finite trace values")
        return trace

    def safe_shutdown(self) -> None:
        self.abort()
        self.set_sweep_mode(VnaSweepMode.HOLD)
        self.set_output(False)
