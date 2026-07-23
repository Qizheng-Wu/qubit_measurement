"""Resolve engineering defaults into complete sweep models."""

from __future__ import annotations

import numpy as np

from control.config import SpectrumSweepDefaults, VnaSweepDefaults
from control.core.exceptions import ValidationError
from control.domain.sweep import (
    ResolvedSpectrumSweep,
    ResolvedVnaSweep,
    SpectrumSweepConfig,
    VnaSweepConfig,
)


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
