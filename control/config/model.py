"""Immutable hardware inventory and shared engineering defaults."""

from __future__ import annotations

from types import MappingProxyType
from typing import Annotated, Literal, Mapping, TypeVar

from pydantic import Field, field_validator, model_validator

from control.core.exceptions import ConfigurationError
from control.core.model import FrozenModel

PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class VisaDeviceConfig(FrozenModel):
    address: Annotated[str, Field(min_length=1)]
    transport_timeout_s: PositiveFloat
    read_termination: str | None
    write_termination: str | None

    @field_validator("read_termination", "write_termination", mode="before")
    @classmethod
    def normalize_disabled_termination(cls, value: object) -> object:
        return None if value == "" else value


class VnaDeviceConfig(VisaDeviceConfig):
    type: Literal["vna"]


class SpectrumAnalyzerDeviceConfig(VisaDeviceConfig):
    type: Literal["spectrum_analyzer"]


class MmcsDacBoardConfig(FrozenModel):
    sample_rate_hz: PositiveFloat


class MmcsSignalPathConfig(FrozenModel):
    dac_board_id: Annotated[str, Field(min_length=1)]
    q_over_i_gain: PositiveFloat
    i_offset: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]
    q_offset: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]
    q_phase_correction_rad: Annotated[float, Field(allow_inf_nan=False)]


class MmcsDeviceConfig(FrozenModel):
    type: Literal["mmcs"]
    boxes: Mapping[str, Annotated[str, Field(min_length=1)]]
    dac_boards: Mapping[str, MmcsDacBoardConfig]
    signal_paths: Mapping[str, MmcsSignalPathConfig]

    @model_validator(mode="after")
    def freeze_inventory(self) -> "MmcsDeviceConfig":
        if not self.boxes or not self.dac_boards or not self.signal_paths:
            raise ValueError("MMCS boxes, dac_boards, and signal_paths must be non-empty")
        if any(not name.strip() for name in (*self.boxes, *self.dac_boards, *self.signal_paths)):
            raise ValueError("MMCS box, DAC board, and signal path names must be non-empty")
        unknown_boards = {
            path.dac_board_id for path in self.signal_paths.values()
            if path.dac_board_id not in self.dac_boards
        }
        if unknown_boards:
            raise ValueError(f"Signal paths reference unknown DAC boards: {sorted(unknown_boards)!r}")
        object.__setattr__(self, "boxes", MappingProxyType(dict(self.boxes)))
        object.__setattr__(self, "dac_boards", MappingProxyType(dict(self.dac_boards)))
        object.__setattr__(self, "signal_paths", MappingProxyType(dict(self.signal_paths)))
        return self

    def require_dac_board(self, board_id: str) -> MmcsDacBoardConfig:
        try:
            return self.dac_boards[board_id]
        except KeyError as exc:
            available = ", ".join(sorted(self.dac_boards))
            raise ConfigurationError(
                f"MMCS DAC board {board_id!r} is not configured; available: {available}"
            ) from exc

    def require_signal_path(self, name: str) -> MmcsSignalPathConfig:
        try:
            return self.signal_paths[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.signal_paths))
            raise ConfigurationError(
                f"MMCS signal path {name!r} is not configured; available: {available}"
            ) from exc


class VnaSweepDefaults(FrozenModel):
    points: Annotated[int, Field(ge=2)]
    bandwidth_hz: PositiveFloat
    averages: Annotated[int, Field(ge=1)]
    acquisition_timeout_s: PositiveFloat


class SpectrumSweepDefaults(FrozenModel):
    points: Annotated[int, Field(ge=2)]
    rbw_span_ratio: PositiveFloat
    input_attenuation_db: NonNegativeFloat
    acquisition_timeout_s: PositiveFloat


class MmcsExecutionDefaults(FrozenModel):
    cleanup_timeout_s: PositiveFloat


class MmcsAwgDefaults(FrozenModel):
    minimum_waveform_samples: Annotated[int, Field(ge=8)]
    period_ns: Annotated[int, Field(ge=4)]
    start_trigger_ns: Annotated[int, Field(ge=4)]
    safety_margin_s: PositiveFloat

    @model_validator(mode="after")
    def validate_trigger_window(self) -> "MmcsAwgDefaults":
        if self.period_ns % 4 or self.start_trigger_ns % 4:
            raise ValueError("period_ns and start_trigger_ns must be multiples of 4")
        if self.start_trigger_ns >= self.period_ns - 4:
            raise ValueError("period_ns must leave room for START and STOP triggers")
        return self


class ControlDefaults(FrozenModel):
    vna_sweep: VnaSweepDefaults
    spectrum_sweep: SpectrumSweepDefaults
    mmcs_execution: MmcsExecutionDefaults
    mmcs_awg: MmcsAwgDefaults


DeviceConfig = Annotated[
    VnaDeviceConfig | SpectrumAnalyzerDeviceConfig | MmcsDeviceConfig,
    Field(discriminator="type"),
]
DeviceConfigT = TypeVar(
    "DeviceConfigT",
    VnaDeviceConfig,
    SpectrumAnalyzerDeviceConfig,
    MmcsDeviceConfig,
)


class ControlConfig(FrozenModel):
    schema_version: Literal[3]
    instruments: Mapping[str, DeviceConfig]
    defaults: ControlDefaults

    @field_validator("instruments", mode="after")
    @classmethod
    def freeze_instruments(cls, value: Mapping[str, DeviceConfig]) -> Mapping[str, DeviceConfig]:
        if not value:
            raise ValueError("instruments must be non-empty")
        if any(not name.strip() for name in value):
            raise ValueError("instrument names must be non-empty")
        return MappingProxyType(dict(value))

    def require(self, name: str, expected_type: type[DeviceConfigT]) -> DeviceConfigT:
        try:
            device = self.instruments[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.instruments))
            raise ConfigurationError(
                f"Instrument {name!r} is not configured; available: {available}"
            ) from exc
        if not isinstance(device, expected_type):
            raise ConfigurationError(
                f"Instrument {name!r} has type {device.type!r}, "
                f"expected {expected_type.__name__}"
            )
        return device
