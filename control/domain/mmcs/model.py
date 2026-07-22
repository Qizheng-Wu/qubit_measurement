"""Immutable, validated MMCS program models."""

from __future__ import annotations

import hashlib
from enum import Enum, IntEnum
from typing import Any

import numpy as np
from pydantic import field_validator, model_validator

from control.core.model import FrozenModel


def _readonly_float_array(values: Any) -> np.ndarray:
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


def _validate_triggers(triggers: tuple[TriggerEvent, ...], period_ns: int, *, adc: bool) -> None:
    if not triggers:
        raise ValueError("Every MMCS board program requires at least one trigger")
    times = [event.time_ns for event in triggers]
    if any(value <= 0 or value % 4 for value in times):
        raise ValueError("Trigger times must be positive multiples of 4 ns")
    if any(current <= previous for previous, current in zip(times, times[1:])):
        raise ValueError("Trigger times must be strictly increasing")
    if times[-1] >= period_ns:
        raise ValueError("Trigger times must be earlier than period_ns")
    if adc and any(event.command is not TriggerCommand.START for event in triggers):
        raise ValueError("ADC trigger events only support START")


class MmcsProgram(FrozenModel):
    master_box: str
    period_ns: int
    repetitions: int
    dac_programs: tuple[DacProgram, ...] = ()
    adc_programs: tuple[AdcProgram, ...] = ()

    @model_validator(mode="after")
    def validate_program(self) -> "MmcsProgram":
        if not self.master_box:
            raise ValueError("master_box cannot be empty")
        if self.period_ns <= 0 or self.period_ns % 4:
            raise ValueError("period_ns must be a positive multiple of 4")
        if self.repetitions < 1:
            raise ValueError("repetitions must be at least 1")
        if not self.dac_programs and not self.adc_programs:
            raise ValueError("MMCS program cannot be empty")

        channel_keys: set[tuple[str, DacChannel]] = set()
        for dac in self.dac_programs:
            key = (dac.board_id, dac.channel)
            if not dac.board_id or key in channel_keys:
                raise ValueError(f"Duplicate or empty DAC channel: {key!r}")
            channel_keys.add(key)
            if not dac.waveforms or not dac.playlist:
                raise ValueError(f"DAC {key!r} requires waveforms and a playlist")
            for waveform in dac.waveforms:
                values = waveform.samples
                if values.ndim != 1 or values.size == 0 or values.size % 8:
                    raise ValueError("DAC waveforms must be non-empty 1-D arrays aligned to 8 samples")
                if not np.all(np.isfinite(values)) or np.any(np.abs(values) > 1):
                    raise ValueError("DAC waveform samples must be finite and within [-1, 1]")
            for entry in dac.playlist:
                if entry.trigger is not TriggerCommand.START:
                    raise ValueError("MMCS v1 playlists only support START entries")
                if not 0 <= entry.waveform_index < len(dac.waveforms):
                    raise ValueError("Playlist waveform index is out of range")
            _validate_triggers(dac.triggers, self.period_ns, adc=False)
            if dac.play_mode is DacPlayMode.CYCLE and not any(
                event.command is TriggerCommand.STOP for event in dac.triggers
            ):
                raise ValueError("Cyclic DAC playback requires a STOP trigger")

        adc_ids: set[str] = set()
        for adc in self.adc_programs:
            if not adc.board_id or adc.board_id in adc_ids:
                raise ValueError(f"Duplicate or empty ADC board: {adc.board_id!r}")
            adc_ids.add(adc.board_id)
            if not 4 <= adc.sample_length <= 8000 or adc.sample_length % 4:
                raise ValueError("ADC sample_length must be aligned to 4 and in [4, 8000]")
            channels: set[int] = set()
            for weights in adc.demodulations:
                if weights.channel not in range(12) or weights.channel in channels:
                    raise ValueError("Demodulation channels must be unique integers in [0, 11]")
                channels.add(weights.channel)
                if weights.i.ndim != 1 or weights.q.ndim != 1:
                    raise ValueError("Demodulation weights must be 1-D")
                if weights.i.size != adc.sample_length or weights.q.size != adc.sample_length:
                    raise ValueError("Demodulation weight length must equal ADC sample_length")
                if not np.all(np.isfinite(weights.i)) or not np.all(np.isfinite(weights.q)):
                    raise ValueError("Demodulation weights must be finite")
                if np.any(np.abs(weights.i) > 1) or np.any(np.abs(weights.q) > 1):
                    raise ValueError("Demodulation weights must be within [-1, 1]")
            _validate_triggers(adc.triggers, self.period_ns, adc=True)
        return self

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
