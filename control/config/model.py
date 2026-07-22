"""Immutable hardware inventory and shared engineering defaults."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar, Literal, Mapping, TypeVar

from control.core.exceptions import ConfigurationError


def _positive(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be finite and positive")
    return value


def _non_negative(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ConfigurationError(f"{name} must be finite and non-negative")
    return value


def _integer(value, minimum: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigurationError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class VisaConnectionConfig:
    address: str
    transport_timeout_s: float = 10.0
    read_termination: str | None = "\n"
    write_termination: str | None = "\n"

    def __post_init__(self) -> None:
        if not isinstance(self.address, str) or not self.address.strip():
            raise ConfigurationError("VISA address must be a non-empty string")
        object.__setattr__(
            self,
            "transport_timeout_s",
            _positive(self.transport_timeout_s, "transport_timeout_s"),
        )
        for name in ("read_termination", "write_termination"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ConfigurationError(f"{name} must be a string or null")


@dataclass(frozen=True, slots=True)
class VnaDeviceConfig:
    connection: VisaConnectionConfig
    type: ClassVar[Literal["vna"]] = "vna"


@dataclass(frozen=True, slots=True)
class SpectrumAnalyzerDeviceConfig:
    connection: VisaConnectionConfig
    type: ClassVar[Literal["spectrum_analyzer"]] = "spectrum_analyzer"


@dataclass(frozen=True, slots=True)
class MmcsDacBoardConfig:
    sample_rate_hz: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_rate_hz", _positive(self.sample_rate_hz, "sample_rate_hz"))


@dataclass(frozen=True, slots=True)
class MmcsDeviceConfig:
    boxes: Mapping[str, str]
    dac_boards: Mapping[str, MmcsDacBoardConfig]
    type: ClassVar[Literal["mmcs"]] = "mmcs"

    def __post_init__(self) -> None:
        boxes = dict(self.boxes)
        boards = dict(self.dac_boards)
        if not boxes:
            raise ConfigurationError("MMCS boxes must be a non-empty mapping")
        if not boards:
            raise ConfigurationError("MMCS dac_boards must be a non-empty mapping")
        if not all(
            isinstance(name, str) and name.strip() and isinstance(address, str) and address.strip()
            for name, address in boxes.items()
        ):
            raise ConfigurationError("MMCS box names and addresses must be non-empty strings")
        if not all(
            isinstance(name, str) and name.strip() and isinstance(board, MmcsDacBoardConfig)
            for name, board in boards.items()
        ):
            raise ConfigurationError("MMCS DAC board names must be non-empty strings")
        object.__setattr__(self, "boxes", MappingProxyType(boxes))
        object.__setattr__(self, "dac_boards", MappingProxyType(boards))

    def require_dac_board(self, board_id: str) -> MmcsDacBoardConfig:
        try:
            return self.dac_boards[board_id]
        except KeyError as exc:
            available = ", ".join(sorted(self.dac_boards))
            raise ConfigurationError(
                f"MMCS DAC board {board_id!r} is not configured; available: {available}"
            ) from exc


@dataclass(frozen=True, slots=True)
class VnaSweepDefaults:
    points: int = 1001
    bandwidth_hz: float = 1e3
    averages: int = 1
    acquisition_timeout_s: float = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", _integer(self.points, 2, "points"))
        object.__setattr__(self, "bandwidth_hz", _positive(self.bandwidth_hz, "bandwidth_hz"))
        object.__setattr__(self, "averages", _integer(self.averages, 1, "averages"))
        object.__setattr__(self, "acquisition_timeout_s", _positive(self.acquisition_timeout_s, "acquisition_timeout_s"))


@dataclass(frozen=True, slots=True)
class SpectrumSweepDefaults:
    points: int = 501
    rbw_span_ratio: float = 0.01
    input_attenuation_db: float = 20.0
    acquisition_timeout_s: float = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", _integer(self.points, 2, "points"))
        object.__setattr__(self, "rbw_span_ratio", _positive(self.rbw_span_ratio, "rbw_span_ratio"))
        object.__setattr__(self, "input_attenuation_db", _non_negative(self.input_attenuation_db, "input_attenuation_db"))
        object.__setattr__(self, "acquisition_timeout_s", _positive(self.acquisition_timeout_s, "acquisition_timeout_s"))


@dataclass(frozen=True, slots=True)
class MmcsExecutionDefaults:
    cleanup_timeout_s: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "cleanup_timeout_s", _positive(self.cleanup_timeout_s, "cleanup_timeout_s"))


@dataclass(frozen=True, slots=True)
class MmcsAwgDefaults:
    minimum_waveform_samples: int = 800
    period_ns: int = 1_000_000
    start_trigger_ns: int = 40
    safety_margin_s: float = 5.0

    def __post_init__(self) -> None:
        minimum = _integer(self.minimum_waveform_samples, 8, "minimum_waveform_samples")
        period = _integer(self.period_ns, 4, "period_ns")
        start = _integer(self.start_trigger_ns, 4, "start_trigger_ns")
        if period % 4 or start % 4:
            raise ConfigurationError("period_ns and start_trigger_ns must be multiples of 4")
        if start >= period - 4:
            raise ConfigurationError("period_ns must leave room for START and STOP triggers")
        object.__setattr__(self, "minimum_waveform_samples", minimum)
        object.__setattr__(self, "period_ns", period)
        object.__setattr__(self, "start_trigger_ns", start)
        object.__setattr__(self, "safety_margin_s", _positive(self.safety_margin_s, "safety_margin_s"))


@dataclass(frozen=True, slots=True)
class ControlDefaults:
    vna_sweep: VnaSweepDefaults = field(default_factory=VnaSweepDefaults)
    spectrum_sweep: SpectrumSweepDefaults = field(default_factory=SpectrumSweepDefaults)
    mmcs_execution: MmcsExecutionDefaults = field(default_factory=MmcsExecutionDefaults)
    mmcs_awg: MmcsAwgDefaults = field(default_factory=MmcsAwgDefaults)


DeviceConfig = VnaDeviceConfig | SpectrumAnalyzerDeviceConfig | MmcsDeviceConfig
DeviceConfigT = TypeVar("DeviceConfigT", bound=DeviceConfig)


@dataclass(frozen=True, slots=True)
class ControlConfig:
    schema_version: int
    instruments: Mapping[str, DeviceConfig]
    defaults: ControlDefaults = field(default_factory=ControlDefaults)

    def __post_init__(self) -> None:
        if self.schema_version == 1:
            raise ConfigurationError("schema_version 1 is no longer supported; migrate to schema_version 2")
        if isinstance(self.schema_version, bool) or self.schema_version != 2:
            raise ConfigurationError(f"Unsupported schema_version {self.schema_version!r}; expected 2")
        instruments = dict(self.instruments)
        if not instruments:
            raise ConfigurationError("instruments must be a non-empty mapping")
        if not all(isinstance(name, str) and name.strip() for name in instruments):
            raise ConfigurationError("Instrument names must be non-empty strings")
        object.__setattr__(self, "instruments", MappingProxyType(instruments))

    def require(self, name: str, expected_type: type[DeviceConfigT]) -> DeviceConfigT:
        try:
            device = self.instruments[name]
        except KeyError as exc:
            available = ", ".join(sorted(self.instruments))
            raise ConfigurationError(f"Instrument {name!r} is not configured; available: {available}") from exc
        if not isinstance(device, expected_type):
            raise ConfigurationError(
                f"Instrument {name!r} has type {device.type!r}, expected {expected_type.__name__}"
            )
        return device
