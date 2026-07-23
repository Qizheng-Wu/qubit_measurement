"""Periodic single-tone waveform generation for MMCS DACs."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

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
