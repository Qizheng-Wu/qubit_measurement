"""Immutable sweep descriptions."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from control.core.exceptions import ValidationError
from control.core.model import FrozenModel

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class VnaSweepConfig(FrozenModel):
    start_hz: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    stop_hz: PositiveFloat
    points: Annotated[int, Field(ge=2)]
    bandwidth_hz: PositiveFloat
    power_dbm: Annotated[float, Field(ge=-85, le=10, allow_inf_nan=False)]
    averages: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def validate_range(self) -> "VnaSweepConfig":
        if self.stop_hz <= self.start_hz:
            raise ValueError("stop_hz must be greater than start_hz")
        return self

    @classmethod
    def from_center_span(
        cls,
        *,
        center_hz: float,
        span_hz: float,
        points: int,
        bandwidth_hz: float,
        power_dbm: float,
        averages: int,
    ) -> "VnaSweepConfig":
        if span_hz <= 0:
            raise ValidationError("span_hz must be positive")
        return cls(
            start_hz=center_hz - span_hz / 2,
            stop_hz=center_hz + span_hz / 2,
            points=points,
            bandwidth_hz=bandwidth_hz,
            power_dbm=power_dbm,
            averages=averages,
        )


class SpectrumSweepConfig(FrozenModel):
    start_hz: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    stop_hz: PositiveFloat
    points: Annotated[int, Field(ge=2)]
    resolution_bandwidth_hz: PositiveFloat
    input_attenuation_db: Annotated[float, Field(ge=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def validate_range(self) -> "SpectrumSweepConfig":
        if self.stop_hz <= self.start_hz:
            raise ValueError("stop_hz must be greater than start_hz")
        return self

    @classmethod
    def from_center_span(
        cls,
        *,
        center_hz: float,
        span_hz: float,
        points: int,
        resolution_bandwidth_hz: float,
        input_attenuation_db: float,
    ) -> "SpectrumSweepConfig":
        if span_hz <= 0:
            raise ValidationError("span_hz must be positive")
        return cls(
            start_hz=center_hz - span_hz / 2,
            stop_hz=center_hz + span_hz / 2,
            points=points,
            resolution_bandwidth_hz=resolution_bandwidth_hz,
            input_attenuation_db=input_attenuation_db,
        )


class ResolvedVnaSweep(FrozenModel):
    config: VnaSweepConfig
    acquisition_timeout_s: PositiveFloat


class ResolvedSpectrumSweep(FrozenModel):
    config: SpectrumSweepConfig
    acquisition_timeout_s: PositiveFloat
