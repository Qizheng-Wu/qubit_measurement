"""IQ tone specifications for single-sideband MMCS upconversion."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import Field, model_validator

from control.core.model import FrozenModel

from .model import DacWaveform


class Sideband(str, Enum):
    UPPER = "upper"
    LOWER = "lower"


class IqCalibration(FrozenModel):
    q_over_i_gain: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1.0
    i_offset: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] = 0.0
    q_offset: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] = 0.0
    q_phase_correction_rad: Annotated[float, Field(allow_inf_nan=False)] = 0.0


class IqToneSpec(FrozenModel):
    sample_rate_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    if_frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    amplitude: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    phase_rad: Annotated[float, Field(allow_inf_nan=False)]
    minimum_samples: Annotated[int, Field(ge=8)]
    sideband: Sideband
    calibration: IqCalibration = Field(default_factory=IqCalibration)

    @model_validator(mode="after")
    def below_nyquist(self) -> "IqToneSpec":
        if self.if_frequency_hz >= self.sample_rate_hz / 2:
            raise ValueError("if_frequency_hz must be below the Nyquist frequency")
        return self


class GeneratedIqTone(FrozenModel):
    spec: IqToneSpec
    i_waveform: DacWaveform
    q_waveform: DacWaveform
    actual_if_frequency_hz: float
