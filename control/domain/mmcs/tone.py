"""Periodic single-tone waveform generation for MMCS DACs."""

from __future__ import annotations

import math
from typing import Annotated

import numpy as np
from pydantic import Field, model_validator

from control.core.exceptions import ValidationError
from control.core.model import FrozenModel

from .model import DacWaveform


class SingleToneSpec(FrozenModel):
    sample_rate_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    amplitude: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    phase_rad: Annotated[float, Field(allow_inf_nan=False)]
    minimum_samples: Annotated[int, Field(ge=8)]

    @model_validator(mode="after")
    def below_nyquist(self) -> "SingleToneSpec":
        if self.frequency_hz >= self.sample_rate_hz / 2:
            raise ValueError("frequency_hz must be below the Nyquist frequency")
        return self


class GeneratedSingleTone(FrozenModel):
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
        waveform=DacWaveform(samples=samples),
        actual_frequency_hz=actual_frequency_hz,
    )
