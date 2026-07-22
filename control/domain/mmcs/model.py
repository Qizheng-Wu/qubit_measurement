"""Immutable MMCS program model."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum, IntEnum

import numpy as np


def _readonly_float_array(values) -> np.ndarray:
    array = np.array(values, dtype=float, copy=True)
    array.setflags(write=False)
    return array


class DacChannel(str, Enum):
    I = "i"
    Q = "q"


class DacPlayMode(str, Enum):
    CYCLE = "cycle_play"
    END_WITH_ZERO = "end_with_zero"
    END_WITH_KEEP = "end_with_keep"


class TriggerCommand(IntEnum):
    START = 1
    STOP = 2
    BRANCH0 = 4
    BRANCH1 = 8
    FEEDBACK = 12


@dataclass(frozen=True, slots=True)
class DacWaveform:
    samples: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "samples", _readonly_float_array(self.samples))


@dataclass(frozen=True, slots=True)
class PlaylistEntry:
    waveform_index: int
    trigger: TriggerCommand = TriggerCommand.START


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    time_ns: int
    command: TriggerCommand = TriggerCommand.START


@dataclass(frozen=True, slots=True)
class DacProgram:
    board_id: str
    channel: DacChannel
    waveforms: tuple[DacWaveform, ...]
    playlist: tuple[PlaylistEntry, ...]
    play_mode: DacPlayMode
    triggers: tuple[TriggerEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "waveforms", tuple(self.waveforms))
        object.__setattr__(self, "playlist", tuple(self.playlist))
        object.__setattr__(self, "triggers", tuple(self.triggers))


@dataclass(frozen=True, slots=True)
class DemodulationWeights:
    channel: int
    i: np.ndarray
    q: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "i", _readonly_float_array(self.i))
        object.__setattr__(self, "q", _readonly_float_array(self.q))


@dataclass(frozen=True, slots=True)
class AdcProgram:
    board_id: str
    sample_length: int
    demodulations: tuple[DemodulationWeights, ...]
    triggers: tuple[TriggerEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "demodulations", tuple(self.demodulations))
        object.__setattr__(self, "triggers", tuple(self.triggers))


@dataclass(frozen=True, slots=True)
class MmcsProgram:
    master_box: str
    period_ns: int
    repetitions: int
    dac_programs: tuple[DacProgram, ...] = ()
    adc_programs: tuple[AdcProgram, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "dac_programs", tuple(self.dac_programs))
        object.__setattr__(self, "adc_programs", tuple(self.adc_programs))

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(f"{self.master_box}|{self.period_ns}|{self.repetitions}".encode())
        for program in self.dac_programs:
            digest.update(
                f"D|{program.board_id}|{program.channel.value}|{program.play_mode.value}".encode()
            )
            for waveform in program.waveforms:
                digest.update(np.ascontiguousarray(waveform.samples).tobytes())
            digest.update(repr(program.playlist).encode())
            digest.update(repr(program.triggers).encode())
        for program in self.adc_programs:
            digest.update(f"A|{program.board_id}|{program.sample_length}".encode())
            for weights in program.demodulations:
                digest.update(str(weights.channel).encode())
                digest.update(np.ascontiguousarray(weights.i).tobytes())
                digest.update(np.ascontiguousarray(weights.q).tobytes())
            digest.update(repr(program.triggers).encode())
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class PreparedMmcsProgram:
    program: MmcsProgram
    fingerprint: str
    connection_generation: int
