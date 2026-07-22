"""Resolve physical sweep requests with shared engineering defaults."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from control.config import SpectrumSweepDefaults, VnaSweepDefaults
from control.core.exceptions import ValidationError
from control.domain.sweep import SpectrumSweepConfig, VnaSweepConfig


def _positive_timeout(value: float) -> float:
    if not np.isfinite(value) or value <= 0:
        raise ValidationError("acquisition_timeout_s must be finite and positive")
    return float(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class VnaSweepRequest:
    start_hz: float
    stop_hz: float
    power_dbm: float


@dataclass(frozen=True, slots=True, kw_only=True)
class VnaSweepEngineeringOverrides:
    points: int | None = None
    bandwidth_hz: float | None = None
    averages: int | None = None
    acquisition_timeout_s: float | None = None


@dataclass(frozen=True, slots=True)
class ResolvedVnaSweep:
    config: VnaSweepConfig
    acquisition_timeout_s: float


def resolve_vna_sweep(
    request: VnaSweepRequest,
    defaults: VnaSweepDefaults,
    overrides: VnaSweepEngineeringOverrides | None = None,
) -> ResolvedVnaSweep:
    override = overrides or VnaSweepEngineeringOverrides()
    config = VnaSweepConfig(
        start_hz=request.start_hz,
        stop_hz=request.stop_hz,
        points=defaults.points if override.points is None else override.points,
        bandwidth_hz=defaults.bandwidth_hz if override.bandwidth_hz is None else override.bandwidth_hz,
        power_dbm=request.power_dbm,
        averages=defaults.averages if override.averages is None else override.averages,
    )
    timeout = defaults.acquisition_timeout_s if override.acquisition_timeout_s is None else override.acquisition_timeout_s
    return ResolvedVnaSweep(config, _positive_timeout(timeout))


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrumSweepRequest:
    start_hz: float
    stop_hz: float


@dataclass(frozen=True, slots=True, kw_only=True)
class SpectrumSweepEngineeringOverrides:
    points: int | None = None
    resolution_bandwidth_hz: float | None = None
    input_attenuation_db: float | None = None
    acquisition_timeout_s: float | None = None


@dataclass(frozen=True, slots=True)
class ResolvedSpectrumSweep:
    config: SpectrumSweepConfig
    acquisition_timeout_s: float


def resolve_spectrum_sweep(
    request: SpectrumSweepRequest,
    defaults: SpectrumSweepDefaults,
    overrides: SpectrumSweepEngineeringOverrides | None = None,
) -> ResolvedSpectrumSweep:
    override = overrides or SpectrumSweepEngineeringOverrides()
    span_hz = request.stop_hz - request.start_hz
    rbw_hz = span_hz * defaults.rbw_span_ratio if override.resolution_bandwidth_hz is None else override.resolution_bandwidth_hz
    config = SpectrumSweepConfig(
        start_hz=request.start_hz,
        stop_hz=request.stop_hz,
        points=defaults.points if override.points is None else override.points,
        resolution_bandwidth_hz=rbw_hz,
        input_attenuation_db=defaults.input_attenuation_db if override.input_attenuation_db is None else override.input_attenuation_db,
    )
    timeout = defaults.acquisition_timeout_s if override.acquisition_timeout_s is None else override.acquisition_timeout_s
    return ResolvedSpectrumSweep(config, _positive_timeout(timeout))
