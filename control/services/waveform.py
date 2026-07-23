"""Reusable MMCS waveform synthesis."""

from __future__ import annotations

import math

import numpy as np

from control.core.exceptions import ValidationError
from control.domain.mmcs.model import DacWaveform
from control.domain.mmcs.tone import GeneratedSingleTone, SingleToneSpec


def generate_single_tone(spec: SingleToneSpec) -> GeneratedSingleTone:
    """Generate an aligned waveform containing an integer number of cycles."""

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
