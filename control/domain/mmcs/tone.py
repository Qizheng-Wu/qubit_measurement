"""Periodic single-tone waveform generation for MMCS DACs."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from control.core.exceptions import ValidationError

from .model import DacWaveform


@dataclass(frozen=True, slots=True)
class SingleToneSpec:
    sample_rate_hz: float
    frequency_hz: float
    amplitude: float
    phase_rad: float
    minimum_samples: int

    def __post_init__(self) -> None:
        numeric = (self.sample_rate_hz, self.frequency_hz, self.amplitude, self.phase_rad)
        if not np.isfinite(numeric).all():
            raise ValidationError("Single-tone parameters must be finite")
        if self.sample_rate_hz <= 0:
            raise ValidationError("sample_rate_hz must be positive")
        if not 0 < self.frequency_hz < self.sample_rate_hz / 2:
            raise ValidationError("frequency_hz must be between 0 and the Nyquist frequency")
        if not 0 < self.amplitude <= 1:
            raise ValidationError("amplitude must be in (0, 1]")
        if (
            isinstance(self.minimum_samples, bool)
            or not isinstance(self.minimum_samples, int)
            or self.minimum_samples < 8
        ):
            raise ValidationError("minimum_samples must be an integer >= 8")


@dataclass(frozen=True, slots=True)
class GeneratedSingleTone:
    spec: SingleToneSpec
    waveform: DacWaveform
    actual_frequency_hz: float


def generate_single_tone(spec: SingleToneSpec) -> GeneratedSingleTone:
    """Generate an aligned waveform with an integer number of cycles.

    The requested frequency is quantized to the closest frequency that is
    periodic over an 8-sample-aligned waveform buffer.
    """

    sample_count = math.ceil(spec.minimum_samples / 8) * 8
    minimum_for_one_cycle = math.ceil(spec.sample_rate_hz / spec.frequency_hz)
    sample_count = max(sample_count, math.ceil(minimum_for_one_cycle / 8) * 8)
    cycle_count = max(1, round(spec.frequency_hz * sample_count / spec.sample_rate_hz))
    actual_frequency_hz = cycle_count * spec.sample_rate_hz / sample_count
    if actual_frequency_hz >= spec.sample_rate_hz / 2:
        raise ValidationError("Quantized tone reaches or exceeds the Nyquist frequency")

    phase = 2 * np.pi * cycle_count * np.arange(sample_count) / sample_count
    samples = spec.amplitude * np.sin(phase + spec.phase_rad)
    return GeneratedSingleTone(
        spec=spec,
        waveform=DacWaveform(samples),
        actual_frequency_hz=actual_frequency_hz,
    )
