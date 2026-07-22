"""Resolve and execute VNA and spectrum-analyzer sweeps."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from control.config import SpectrumSweepDefaults, VnaSweepDefaults
from control.core.exceptions import AcquisitionError, ValidationError
from control.core.model import FrozenModel
from control.domain.sweep import SpectrumSweepConfig, VnaSweepConfig
from control.domain.trace import SpectrumTrace, VnaTrace
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver, VnaSweepMode


class ResolvedVnaSweep(FrozenModel):
    config: VnaSweepConfig
    acquisition_timeout_s: float


def resolve_vna_sweep(
    defaults: VnaSweepDefaults,
    *,
    start_hz: float,
    stop_hz: float,
    power_dbm: float,
    points: int | None = None,
    bandwidth_hz: float | None = None,
    averages: int | None = None,
    acquisition_timeout_s: float | None = None,
) -> ResolvedVnaSweep:
    timeout = defaults.acquisition_timeout_s if acquisition_timeout_s is None else acquisition_timeout_s
    if not np.isfinite(timeout) or timeout <= 0:
        raise ValidationError("acquisition_timeout_s must be finite and positive")
    return ResolvedVnaSweep(
        config=VnaSweepConfig(
            start_hz=start_hz,
            stop_hz=stop_hz,
            points=defaults.points if points is None else points,
            bandwidth_hz=defaults.bandwidth_hz if bandwidth_hz is None else bandwidth_hz,
            power_dbm=power_dbm,
            averages=defaults.averages if averages is None else averages,
        ),
        acquisition_timeout_s=float(timeout),
    )


class ResolvedSpectrumSweep(FrozenModel):
    config: SpectrumSweepConfig
    acquisition_timeout_s: float


def resolve_spectrum_sweep(
    defaults: SpectrumSweepDefaults,
    *,
    start_hz: float,
    stop_hz: float,
    points: int | None = None,
    resolution_bandwidth_hz: float | None = None,
    input_attenuation_db: float | None = None,
    acquisition_timeout_s: float | None = None,
) -> ResolvedSpectrumSweep:
    timeout = defaults.acquisition_timeout_s if acquisition_timeout_s is None else acquisition_timeout_s
    if not np.isfinite(timeout) or timeout <= 0:
        raise ValidationError("acquisition_timeout_s must be finite and positive")
    rbw = (
        (stop_hz - start_hz) * defaults.rbw_span_ratio
        if resolution_bandwidth_hz is None
        else resolution_bandwidth_hz
    )
    return ResolvedSpectrumSweep(
        config=SpectrumSweepConfig(
            start_hz=start_hz,
            stop_hz=stop_hz,
            points=defaults.points if points is None else points,
            resolution_bandwidth_hz=rbw,
            input_attenuation_db=(
                defaults.input_attenuation_db
                if input_attenuation_db is None
                else input_attenuation_db
            ),
        ),
        acquisition_timeout_s=float(timeout),
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

    def acquire(self, config: SpectrumSweepConfig, *, timeout_s: float) -> SpectrumTrace:
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
