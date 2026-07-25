"""Specifications and results for automatic IQ mixer calibration."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field, model_validator

from control.core.model import FrozenModel
from control.domain.mmcs import IqCalibration, Sideband


PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class IqAutoCalibrationSpec(FrozenModel):
    signal_path: Annotated[str, Field(min_length=1)]
    board_id: Annotated[str, Field(min_length=1)]
    master_box: Annotated[str, Field(min_length=1)]
    sample_rate_hz: PositiveFloat
    lo_frequency_hz: PositiveFloat
    if_frequency_hz: PositiveFloat
    sideband: Sideband
    amplitude: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
    minimum_samples: Annotated[int, Field(ge=8)]
    period_ns: Annotated[int, Field(ge=8)]
    start_trigger_ns: Annotated[int, Field(ge=4)]
    spectrum_span_hz: PositiveFloat
    spectrum_points: Annotated[int, Field(ge=2)]
    resolution_bandwidth_hz: PositiveFloat
    input_attenuation_db: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    measurement_timeout_s: PositiveFloat
    initial_calibration: IqCalibration
    offset_bounds: tuple[tuple[float, float], tuple[float, float]] = (
        (-0.2, 0.2),
        (-0.2, 0.2),
    )
    imbalance_bounds: tuple[tuple[float, float], tuple[float, float]] = (
        (0.5, 1.5),
        (-0.5, 0.5),
    )
    measurement_repetitions: Annotated[int, Field(ge=1)] = 3
    max_evaluations_per_stage: Annotated[int, Field(ge=4)] = 80
    improvement_tolerance_db: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 0.1
    patience_iterations: Annotated[int, Field(ge=1)] = 3

    @property
    def target_frequency_hz(self) -> float:
        sign = 1 if self.sideband is Sideband.UPPER else -1
        return self.lo_frequency_hz + sign * self.if_frequency_hz

    @property
    def image_frequency_hz(self) -> float:
        sign = -1 if self.sideband is Sideband.UPPER else 1
        return self.lo_frequency_hz + sign * self.if_frequency_hz

    @model_validator(mode="after")
    def validate_calibration_search(self) -> "IqAutoCalibrationSpec":
        if self.if_frequency_hz >= self.sample_rate_hz / 2:
            raise ValueError("if_frequency_hz must be below the Nyquist frequency")
        if min(self.target_frequency_hz, self.image_frequency_hz) <= 0:
            raise ValueError("Target and image frequencies must be positive")
        if self.period_ns % 4 or self.start_trigger_ns % 4:
            raise ValueError("period_ns and start_trigger_ns must be multiples of 4")
        if self.start_trigger_ns >= self.period_ns - 4:
            raise ValueError("period_ns must leave room for START and STOP triggers")
        bounds = (*self.offset_bounds, *self.imbalance_bounds)
        if any(len(bound) != 2 or bound[0] >= bound[1] for bound in bounds):
            raise ValueError("Every calibration bound must be an increasing pair")
        initial = (
            self.initial_calibration.i_offset,
            self.initial_calibration.q_offset,
            self.initial_calibration.q_over_i_gain,
            self.initial_calibration.q_phase_correction_rad,
        )
        if any(not low <= value <= high for value, (low, high) in zip(initial, bounds)):
            raise ValueError("Initial calibration must lie within optimization bounds")
        return self


class IqAutoCalibrationResult(FrozenModel):
    run_id: int
    calibration: IqCalibration
    initial_lo_dbm: float
    final_lo_dbm: float
    initial_target_dbm: float
    final_target_dbm: float
    initial_image_dbm: float
    final_image_dbm: float
    image_rejection_db: float
    optimizer_converged: bool
    termination_reason: str
    offset_evaluations: int
    imbalance_evaluations: int

    def toml_snippet(self, signal_path: str, board_id: str) -> str:
        calibration = self.calibration
        return "\n".join(
            (
                f"[instruments.mmcs.signal_paths.{json.dumps(signal_path)}]",
                f"dac_board_id = {json.dumps(board_id)}",
                f"q_over_i_gain = {calibration.q_over_i_gain:.12g}",
                f"i_offset = {calibration.i_offset:.12g}",
                f"q_offset = {calibration.q_offset:.12g}",
                f"q_phase_correction_rad = {calibration.q_phase_correction_rad:.12g}",
            )
        )
