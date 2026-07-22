"""Immutable models for static instrument connection information."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal, Mapping, TypeVar

from control.core.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class VisaConnectionConfig:
    address: str
    timeout_s: float = 10.0
    read_termination: str | None = "\n"
    write_termination: str | None = "\n"

    def __post_init__(self) -> None:
        if not isinstance(self.address, str) or not self.address.strip():
            raise ConfigurationError("VISA address must be a non-empty string")
        if isinstance(self.timeout_s, bool) or not isinstance(self.timeout_s, (int, float)):
            raise ConfigurationError("VISA timeout_s must be a number")
        if self.timeout_s <= 0:
            raise ConfigurationError("VISA timeout_s must be positive")
        for field_name in ("read_termination", "write_termination"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise ConfigurationError(f"VISA {field_name} must be a string or null")
        object.__setattr__(self, "timeout_s", float(self.timeout_s))


@dataclass(frozen=True, slots=True)
class VnaDeviceConfig:
    connection: VisaConnectionConfig
    type: ClassVar[Literal["vna"]] = "vna"


@dataclass(frozen=True, slots=True)
class SpectrumAnalyzerDeviceConfig:
    connection: VisaConnectionConfig
    type: ClassVar[Literal["spectrum_analyzer"]] = "spectrum_analyzer"


@dataclass(frozen=True, slots=True)
class MmcsDeviceConfig:
    boxes: Mapping[str, str]
    master_box: str = "box1"
    cleanup_timeout_s: float = 5.0
    type: ClassVar[Literal["mmcs"]] = "mmcs"

    def __post_init__(self) -> None:
        boxes = dict(self.boxes)
        if not boxes:
            raise ConfigurationError("MMCS boxes must be a non-empty mapping")
        if not all(
            isinstance(name, str)
            and bool(name.strip())
            and isinstance(address, str)
            and bool(address.strip())
            for name, address in boxes.items()
        ):
            raise ConfigurationError("MMCS box names and addresses must be non-empty strings")
        if not isinstance(self.master_box, str) or self.master_box not in boxes:
            raise ConfigurationError("MMCS master_box must name one of the configured boxes")
        if isinstance(self.cleanup_timeout_s, bool) or not isinstance(
            self.cleanup_timeout_s, (int, float)
        ):
            raise ConfigurationError("MMCS cleanup_timeout_s must be a number")
        if self.cleanup_timeout_s <= 0:
            raise ConfigurationError("MMCS cleanup_timeout_s must be positive")
        object.__setattr__(self, "boxes", MappingProxyType(boxes))
        object.__setattr__(self, "cleanup_timeout_s", float(self.cleanup_timeout_s))


DeviceConfig = VnaDeviceConfig | SpectrumAnalyzerDeviceConfig | MmcsDeviceConfig
DeviceConfigT = TypeVar("DeviceConfigT", bound=DeviceConfig)


@dataclass(frozen=True, slots=True)
class ControlConfig:
    schema_version: int
    instruments: Mapping[str, DeviceConfig]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ConfigurationError(
                f"Unsupported schema_version {self.schema_version!r}; expected 1"
            )
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
            raise ConfigurationError(
                f"Instrument {name!r} is not configured; available: {available}"
            ) from exc
        if not isinstance(device, expected_type):
            raise ConfigurationError(
                f"Instrument {name!r} has type {device.type!r}, "
                f"expected {expected_type.__name__}"
            )
        return device
