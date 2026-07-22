"""Complete, safe sweep workflows for SCPI instruments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from control.core.exceptions import AcquisitionError, ValidationError
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver, VnaSweepMode

from .trace import SpectrumTrace, VnaTrace


def _validate_common(start_hz: float, stop_hz: float, points: int, bandwidth_hz: float) -> None:
    if not np.isfinite([start_hz, stop_hz, bandwidth_hz]).all():
        raise ValidationError("Sweep parameters must be finite")
    if start_hz < 0 or stop_hz <= start_hz:
        raise ValidationError("Sweep requires 0 <= start_hz < stop_hz")
    if not isinstance(points, int) or points < 2:
        raise ValidationError("Sweep points must be an integer >= 2")
    if bandwidth_hz <= 0:
        raise ValidationError("Sweep bandwidth must be positive")


@dataclass(frozen=True, slots=True)
class VnaSweepConfig:
    start_hz: float
    stop_hz: float
    points: int
    bandwidth_hz: float
    power_dbm: float
    averages: int = 1

    def __post_init__(self) -> None:
        _validate_common(self.start_hz, self.stop_hz, self.points, self.bandwidth_hz)
        if not -85 <= self.power_dbm <= 10:
            raise ValidationError("power_dbm must be in [-85, 10]")
        if not isinstance(self.averages, int) or self.averages < 1:
            raise ValidationError("averages must be an integer >= 1")

    @classmethod
    def from_center_span(
        cls,
        *,
        center_hz: float,
        span_hz: float,
        points: int,
        bandwidth_hz: float,
        power_dbm: float,
        averages: int = 1,
    ) -> "VnaSweepConfig":
        if span_hz <= 0:
            raise ValidationError("span_hz must be positive")
        return cls(
            center_hz - span_hz / 2,
            center_hz + span_hz / 2,
            points,
            bandwidth_hz,
            power_dbm,
            averages,
        )


@dataclass(frozen=True, slots=True)
class SpectrumSweepConfig:
    start_hz: float
    stop_hz: float
    points: int
    resolution_bandwidth_hz: float
    input_attenuation_db: float = 0.0

    def __post_init__(self) -> None:
        _validate_common(
            self.start_hz, self.stop_hz, self.points, self.resolution_bandwidth_hz
        )
        if self.input_attenuation_db < 0 or not np.isfinite(self.input_attenuation_db):
            raise ValidationError("input_attenuation_db must be finite and non-negative")

    @classmethod
    def from_center_span(
        cls,
        *,
        center_hz: float,
        span_hz: float,
        points: int,
        resolution_bandwidth_hz: float,
        input_attenuation_db: float = 0.0,
    ) -> "SpectrumSweepConfig":
        if span_hz <= 0:
            raise ValidationError("span_hz must be positive")
        return cls(
            center_hz - span_hz / 2,
            center_hz + span_hz / 2,
            points,
            resolution_bandwidth_hz,
            input_attenuation_db,
        )


class VnaController:
    def __init__(self, driver: VnaDriver) -> None:
        self.driver = driver

    def acquire(self, config: VnaSweepConfig, *, timeout_s: float) -> VnaTrace:
        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        if not self.driver.is_connected:
            raise AcquisitionError("VNA must be connected before acquire()")
        original_output = self.driver.get_output()
        primary_error: BaseException | None = None
        try:
            self.driver.set_start_hz(config.start_hz)
            self.driver.set_stop_hz(config.stop_hz)
            self.driver.set_points(config.points)
            self.driver.set_bandwidth_hz(config.bandwidth_hz)
            self.driver.set_power_dbm(config.power_dbm)
            self.driver.set_averages(config.averages)
            self.driver.set_output(True)
            self.driver.clear_averages()
            self.driver.arm_bus_trigger()
            self.driver.trigger()
            self.driver.wait_operation_complete(timeout_s)
            data = self.driver.fetch_complex_trace(expected_points=config.points)
            return VnaTrace(
                frequency_hz=np.linspace(config.start_hz, config.stop_hz, config.points),
                s_parameter=data,
                config=config,
                instrument=self.driver.identity,
                acquired_at=datetime.now(timezone.utc),
            )
        except BaseException as exc:
            primary_error = exc
            try:
                self.driver.abort()
            except Exception as cleanup_exc:
                exc.add_note(f"VNA abort also failed: {cleanup_exc}")
            raise
        finally:
            try:
                self.driver.set_sweep_mode(VnaSweepMode.HOLD)
                self.driver.set_output(original_output)
            except Exception as cleanup_exc:
                if primary_error is not None:
                    primary_error.add_note(f"Restoring VNA state also failed: {cleanup_exc}")
                else:
                    raise AcquisitionError("VNA acquired data but failed to restore state") from cleanup_exc


class SpectrumAnalyzerController:
    def __init__(self, driver: SpectrumAnalyzerDriver) -> None:
        self.driver = driver

    def acquire(
        self, config: SpectrumSweepConfig, *, timeout_s: float
    ) -> SpectrumTrace:
        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        if not self.driver.is_connected:
            raise AcquisitionError("Spectrum analyzer must be connected before acquire()")
        primary_error: BaseException | None = None
        try:
            self.driver.set_start_hz(config.start_hz)
            self.driver.set_stop_hz(config.stop_hz)
            self.driver.set_points(config.points)
            self.driver.set_resolution_bandwidth_hz(config.resolution_bandwidth_hz)
            self.driver.set_input_attenuation_db(config.input_attenuation_db)
            self.driver.set_continuous(False)
            self.driver.trigger()
            self.driver.wait_operation_complete(timeout_s)
            power = self.driver.fetch_trace_dbm(expected_points=config.points)
            return SpectrumTrace(
                frequency_hz=np.linspace(config.start_hz, config.stop_hz, config.points),
                power_dbm=power,
                config=config,
                instrument=self.driver.identity,
                acquired_at=datetime.now(timezone.utc),
            )
        except BaseException as exc:
            primary_error = exc
            try:
                self.driver.abort()
            except Exception as cleanup_exc:
                exc.add_note(f"Spectrum analyzer abort also failed: {cleanup_exc}")
            raise
        finally:
            try:
                self.driver.set_continuous(False)
            except Exception as cleanup_exc:
                if primary_error is not None:
                    primary_error.add_note(
                        f"Restoring spectrum-analyzer state also failed: {cleanup_exc}"
                    )
                else:
                    raise AcquisitionError(
                        "Spectrum analyzer acquired data but failed to restore state"
                    ) from cleanup_exc
