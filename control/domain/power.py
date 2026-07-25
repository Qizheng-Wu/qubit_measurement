"""Scalar spectrum-analyzer power measurements."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, model_validator

from control.core.model import FrozenModel


class ScalarPowerMeasurementConfig(FrozenModel):
    frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    span_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    points: Annotated[int, Field(ge=2)]
    resolution_bandwidth_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    input_attenuation_db: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    marker: Annotated[int, Field(ge=1, le=16)] = 1

    @model_validator(mode="after")
    def positive_start_frequency(self) -> "ScalarPowerMeasurementConfig":
        if self.frequency_hz - self.span_hz / 2 < 0:
            raise ValueError("Scalar power span must not extend below 0 Hz")
        return self


class ScalarPowerResult(FrozenModel):
    frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    power_dbm: Annotated[float, Field(allow_inf_nan=False)]
    readings_dbm: Annotated[
        tuple[Annotated[float, Field(allow_inf_nan=False)], ...],
        Field(min_length=1),
    ]
    acquired_at: datetime

    @model_validator(mode="after")
    def require_aware_timestamp(self) -> "ScalarPowerResult":
        if self.acquired_at.tzinfo is None:
            raise ValueError("acquired_at must be timezone-aware")
        return self
