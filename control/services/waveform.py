"""Reusable MMCS waveform synthesis."""

from __future__ import annotations

import math

import numpy as np

from control.core.exceptions import ValidationError
from control.domain.mmcs.iq_tone import GeneratedIqTone, IqToneSpec, Sideband
from control.domain.mmcs.model import DacWaveform
from control.domain.mmcs.tone import GeneratedSingleTone, SingleToneSpec


def _quantize_periodic_tone(
    *, sample_rate_hz: float, frequency_hz: float, minimum_samples: int
) -> tuple[int, int, float]:
    sample_count = math.ceil(minimum_samples / 8) * 8
    minimum_for_one_cycle = math.ceil(sample_rate_hz / frequency_hz)
    sample_count = max(sample_count, math.ceil(minimum_for_one_cycle / 8) * 8)
    cycle_count = max(1, round(frequency_hz * sample_count / sample_rate_hz))
    actual_frequency_hz = cycle_count * sample_rate_hz / sample_count
    if actual_frequency_hz >= sample_rate_hz / 2:
        raise ValidationError("Quantized tone reaches or exceeds the Nyquist frequency")
    return sample_count, cycle_count, actual_frequency_hz


def generate_single_tone(spec: SingleToneSpec) -> GeneratedSingleTone:
    """Generate an aligned waveform containing an integer number of cycles."""

    sample_count, cycle_count, actual_frequency_hz = _quantize_periodic_tone(
        sample_rate_hz=spec.sample_rate_hz,
        frequency_hz=spec.frequency_hz,
        minimum_samples=spec.minimum_samples,
    )

    phase = 2 * np.pi * cycle_count * np.arange(sample_count) / sample_count
    samples = spec.amplitude * np.sin(phase + spec.phase_rad)
    return GeneratedSingleTone(
        spec=spec,
        waveform=DacWaveform(samples=samples),
        actual_frequency_hz=actual_frequency_hz,
    )


def generate_iq_tone(spec: IqToneSpec) -> GeneratedIqTone:
    """Generate a calibrated periodic IQ pair for single-sideband upconversion."""

    sample_count, cycle_count, actual_frequency_hz = _quantize_periodic_tone(
        sample_rate_hz=spec.sample_rate_hz,
        frequency_hz=spec.if_frequency_hz,
        minimum_samples=spec.minimum_samples,
    )
    phase = (
        2 * np.pi * cycle_count * np.arange(sample_count) / sample_count + spec.phase_rad
    )
    calibration = spec.calibration
    sideband_sign = 1 if spec.sideband is Sideband.UPPER else -1
    i_samples = calibration.i_offset + spec.amplitude * np.cos(phase)
    q_samples = (
        calibration.q_offset
        + spec.amplitude
        * calibration.q_over_i_gain
        * sideband_sign
        * np.sin(phase + calibration.q_phase_correction_rad)
    )
    if np.any(np.abs(i_samples) > 1) or np.any(np.abs(q_samples) > 1):
        raise ValidationError("Calibrated IQ waveform exceeds the normalized DAC range [-1, 1]")
    return GeneratedIqTone(
        spec=spec,
        i_waveform=DacWaveform(samples=i_samples),
        q_waveform=DacWaveform(samples=q_samples),
        actual_if_frequency_hz=actual_frequency_hz,
    )
