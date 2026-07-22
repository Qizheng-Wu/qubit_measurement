"""Immutable MMCS program model."""

from __future__ import annotations

import hashlib
from enum import Enum, IntEnum
from typing import Any

import numpy as np
from pydantic import field_validator

from control.core.model import FrozenModel


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


class DacWaveform(FrozenModel):
    samples: np.ndarray

    @field_validator("samples", mode="before")
    @classmethod
    def make_samples_readonly(cls, value: Any) -> np.ndarray:
        return _readonly_float_array(value)


class PlaylistEntry(FrozenModel):
    waveform_index: int
    trigger: TriggerCommand


class TriggerEvent(FrozenModel):
    time_ns: int
    command: TriggerCommand


class DacProgram(FrozenModel):
    board_id: str
    channel: DacChannel
    waveforms: tuple[DacWaveform, ...]
    playlist: tuple[PlaylistEntry, ...]
    play_mode: DacPlayMode
    triggers: tuple[TriggerEvent, ...]

    @field_validator("waveforms", "playlist", "triggers", mode="before")
    @classmethod
    def freeze_sequences(cls, value: Any) -> tuple[Any, ...]:
        return tuple(value)


class DemodulationWeights(FrozenModel):
    channel: int
    i: np.ndarray
    q: np.ndarray

    @field_validator("i", "q", mode="before")
    @classmethod
    def make_weights_readonly(cls, value: Any) -> np.ndarray:
        return _readonly_float_array(value)


class AdcProgram(FrozenModel):
    board_id: str
    sample_length: int
    demodulations: tuple[DemodulationWeights, ...]
    triggers: tuple[TriggerEvent, ...]

    @field_validator("demodulations", "triggers", mode="before")
    @classmethod
    def freeze_sequences(cls, value: Any) -> tuple[Any, ...]:
        return tuple(value)


class MmcsProgram(FrozenModel):
    master_box: str
    period_ns: int
    repetitions: int
    dac_programs: tuple[DacProgram, ...] = ()
    adc_programs: tuple[AdcProgram, ...] = ()

    @field_validator("dac_programs", "adc_programs", mode="before")
    @classmethod
    def freeze_sequences(cls, value: Any) -> tuple[Any, ...]:
        return tuple(value)

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


class PreparedMmcsProgram(FrozenModel):
    program: MmcsProgram
    fingerprint: str
    connection_generation: int


class RunningMmcsProgram(FrozenModel):
    """A prepared program that has been started by an executor."""

    prepared: PreparedMmcsProgram
    started_at_s: float
