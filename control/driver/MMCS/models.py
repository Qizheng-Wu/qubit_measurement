"""Public value objects and hardware constraints for MMCS v1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from ipaddress import IPv4Address
from types import MappingProxyType
from typing import Iterable, Mapping

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .errors import ValidationError


class DacPair(str, Enum):
    CH12 = "12"
    CH34 = "34"


class DacLane(str, Enum):
    I = "i"
    Q = "q"


class PlayMode(str, Enum):
    CYCLE = "cycle_play"
    ZERO_AFTER = "end_with_zero"
    HOLD_LAST = "end_with_keep"


class TriggerCommand(IntEnum):
    START = 1
    STOP = 2


@dataclass(frozen=True, slots=True)
class BoxConfig:
    name: str
    ip: str
    port: int = 6002

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or any(c.isspace() for c in self.name):
            raise ValidationError("box name must be a non-empty string without whitespace")
        try:
            parsed = IPv4Address(self.ip)
        except ValueError as exc:
            raise ValidationError(f"invalid IPv4 address: {self.ip!r}") from exc
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValidationError("box port must be an integer in [1, 65535]")
        object.__setattr__(self, "ip", str(parsed))


@dataclass(frozen=True, slots=True)
class DacAddress:
    box: str
    slot: int
    pair: DacPair

    def __post_init__(self) -> None:
        if not isinstance(self.box, str) or not self.box:
            raise ValidationError("DAC box name must be non-empty")
        if isinstance(self.slot, bool) or not isinstance(self.slot, int) or not 1 <= self.slot <= 14:
            raise ValidationError("DAC slot must be an integer in [1, 14]")
        if not isinstance(self.pair, DacPair):
            raise ValidationError("DAC pair must be DacPair.CH12 or DacPair.CH34")


def _normalized_wave(value: ArrayLike, *, name: str) -> NDArray[np.float64]:
    if np.iscomplexobj(value):
        raise ValidationError(f"{name} must contain real values")
    try:
        wave = np.array(value, dtype=np.float64, copy=True, order="C")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a one-dimensional numeric array") from exc
    if wave.ndim != 1:
        raise ValidationError(f"{name} must be one-dimensional")
    if wave.size == 0:
        raise ValidationError(f"{name} must not be empty")
    if wave.size % 8:
        raise ValidationError(f"{name} length must be a multiple of 8")
    if not np.isfinite(wave).all():
        raise ValidationError(f"{name} must not contain NaN or infinity")
    if np.any((wave < -1.0) | (wave > 1.0)):
        raise ValidationError(f"{name} values must be within [-1, 1]")
    wave.flags.writeable = False
    return wave


@dataclass(frozen=True, slots=True)
class WaveSegment:
    i: NDArray[np.float64]
    q: NDArray[np.float64]

    def __init__(self, i: ArrayLike, q: ArrayLike) -> None:
        i_wave = _normalized_wave(i, name="I waveform")
        q_wave = _normalized_wave(q, name="Q waveform")
        if i_wave.size != q_wave.size:
            raise ValidationError("I and Q waveforms must have equal lengths")
        object.__setattr__(self, "i", i_wave)
        object.__setattr__(self, "q", q_wave)

    @property
    def length(self) -> int:
        return int(self.i.size)


@dataclass(frozen=True, slots=True)
class DacSequence:
    segments: tuple[WaveSegment, ...]
    mode: PlayMode = PlayMode.ZERO_AFTER

    def __init__(self, segments: Iterable[WaveSegment], mode: PlayMode = PlayMode.ZERO_AFTER) -> None:
        values = tuple(segments)
        if not values:
            raise ValidationError("a DAC sequence must contain at least one segment")
        if not all(isinstance(segment, WaveSegment) for segment in values):
            raise ValidationError("all DAC sequence entries must be WaveSegment objects")
        if not isinstance(mode, PlayMode):
            raise ValidationError("mode must be a PlayMode value")
        object.__setattr__(self, "segments", values)
        object.__setattr__(self, "mode", mode)

    @classmethod
    def single(
        cls,
        i: ArrayLike,
        q: ArrayLike,
        mode: PlayMode = PlayMode.ZERO_AFTER,
    ) -> "DacSequence":
        return cls((WaveSegment(i, q),), mode)


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    at_ns: int
    command: TriggerCommand = TriggerCommand.START

    def __post_init__(self) -> None:
        if isinstance(self.at_ns, bool) or not isinstance(self.at_ns, int):
            raise ValidationError("trigger timestamp must be an integer number of nanoseconds")
        if not isinstance(self.command, TriggerCommand):
            raise ValidationError("command must be a supported TriggerCommand")


@dataclass(frozen=True, slots=True)
class TriggerProgram:
    period_ns: int
    repetitions: int
    master_box: str
    channels: Mapping[DacAddress, tuple[TriggerEvent, ...]]

    def __init__(
        self,
        period_ns: int,
        repetitions: int,
        master_box: str,
        channels: Mapping[DacAddress, Iterable[TriggerEvent]],
    ) -> None:
        if isinstance(period_ns, bool) or not isinstance(period_ns, int) or period_ns <= 0:
            raise ValidationError("period_ns must be a positive integer")
        if period_ns % 4:
            raise ValidationError("period_ns must be a multiple of 4 ns")
        if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions <= 0:
            raise ValidationError("repetitions must be a positive integer; infinite runs are not supported")
        if not isinstance(master_box, str) or not master_box:
            raise ValidationError("master_box must be non-empty")
        if not channels:
            raise ValidationError("a trigger program must contain at least one DAC channel")

        normalized: dict[DacAddress, tuple[TriggerEvent, ...]] = {}
        for address, channel_events in channels.items():
            if not isinstance(address, DacAddress):
                raise ValidationError("trigger channel keys must be DacAddress objects")
            events = tuple(channel_events)
            if not events:
                raise ValidationError(f"trigger channel {address} must contain at least one event")
            previous = 0
            for event in events:
                if not isinstance(event, TriggerEvent):
                    raise ValidationError("trigger events must be TriggerEvent objects")
                if event.at_ns <= 0:
                    raise ValidationError("trigger timestamps must be greater than zero")
                if event.at_ns % 4:
                    raise ValidationError("trigger timestamps must be multiples of 4 ns")
                if event.at_ns >= period_ns:
                    raise ValidationError("trigger timestamps must be smaller than period_ns")
                if event.at_ns <= previous:
                    raise ValidationError("trigger timestamps must be strictly increasing per channel")
                previous = event.at_ns
            normalized[address] = events

        object.__setattr__(self, "period_ns", period_ns)
        object.__setattr__(self, "repetitions", repetitions)
        object.__setattr__(self, "master_box", master_box)
        object.__setattr__(self, "channels", MappingProxyType(normalized))

    @classmethod
    def single(
        cls,
        *,
        dac: DacAddress,
        trigger_ns: int,
        period_ns: int,
        repetitions: int,
        master_box: str,
    ) -> "TriggerProgram":
        return cls(
            period_ns=period_ns,
            repetitions=repetitions,
            master_box=master_box,
            channels={dac: (TriggerEvent(trigger_ns),)},
        )


@dataclass(frozen=True, slots=True)
class Inventory:
    boxes: tuple[BoxConfig, ...]
    dacs: tuple[DacAddress, ...]
    vendor_names: Mapping[DacAddress, str]

    def __init__(
        self,
        boxes: Iterable[BoxConfig],
        dacs: Iterable[DacAddress],
        vendor_names: Mapping[DacAddress, str] | None = None,
    ) -> None:
        box_values = tuple(boxes)
        dac_values = tuple(sorted(dacs, key=lambda item: (item.box, item.slot, item.pair.value)))
        names = dict(vendor_names or {})
        if set(names) - set(dac_values):
            raise ValidationError("vendor_names contains an undiscovered DAC address")
        object.__setattr__(self, "boxes", box_values)
        object.__setattr__(self, "dacs", dac_values)
        object.__setattr__(self, "vendor_names", MappingProxyType(names))
