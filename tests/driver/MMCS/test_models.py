from __future__ import annotations

import numpy as np
import pytest

from control.driver.MMCS import (
    BoxConfig,
    DacAddress,
    DacPair,
    DacSequence,
    PlayMode,
    TriggerEvent,
    TriggerProgram,
    ValidationError,
    WaveSegment,
)


@pytest.mark.parametrize(
    "value",
    [[], np.zeros(7), np.zeros((2, 8)), np.full(8, np.nan), np.full(8, np.inf), np.full(8, 1.01)],
)
def test_wave_segment_rejects_invalid_i_wave(value) -> None:
    with pytest.raises(ValidationError):
        WaveSegment(value, np.zeros(8))


def test_wave_segment_copies_and_freezes_input() -> None:
    source_i = np.linspace(-1, 1, 8)
    segment = WaveSegment(source_i, np.zeros(8))
    source_i[:] = 0.5
    assert segment.i[0] == -1
    assert not segment.i.flags.writeable


def test_wave_segment_requires_equal_iq_lengths() -> None:
    with pytest.raises(ValidationError, match="equal lengths"):
        WaveSegment(np.zeros(8), np.zeros(16))


def test_sequence_requires_segments_and_enum_mode() -> None:
    with pytest.raises(ValidationError):
        DacSequence(())
    with pytest.raises(ValidationError):
        DacSequence((WaveSegment(np.zeros(8), np.zeros(8)),), "end_with_zero")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"period_ns": 10, "repetitions": 1, "master_box": "box1"},
        {"period_ns": 100, "repetitions": 0, "master_box": "box1"},
        {"period_ns": 100, "repetitions": 1, "master_box": ""},
    ],
)
def test_trigger_program_rejects_invalid_header(kwargs) -> None:
    address = DacAddress("box1", 1, DacPair.CH12)
    with pytest.raises(ValidationError):
        TriggerProgram(channels={address: (TriggerEvent(4),)}, **kwargs)


@pytest.mark.parametrize(
    "events",
    [
        (TriggerEvent(0),),
        (TriggerEvent(6),),
        (TriggerEvent(100),),
        (TriggerEvent(8), TriggerEvent(4)),
        (TriggerEvent(4), TriggerEvent(4)),
    ],
)
def test_trigger_program_rejects_invalid_events(events) -> None:
    address = DacAddress("box1", 1, DacPair.CH12)
    with pytest.raises(ValidationError):
        TriggerProgram(100, 1, "box1", {address: events})


def test_public_single_program() -> None:
    address = DacAddress("box1", 3, DacPair.CH12)
    program = TriggerProgram.single(
        dac=address,
        trigger_ns=40,
        period_ns=10_000,
        repetitions=5,
        master_box="box1",
    )
    assert program.channels[address] == (TriggerEvent(40),)
    assert program.repetitions == 5


def test_box_and_address_validation() -> None:
    with pytest.raises(ValidationError):
        BoxConfig("box 1", "192.168.4.8")
    with pytest.raises(ValidationError):
        BoxConfig("box1", "not-an-ip")
    with pytest.raises(ValidationError):
        DacAddress("box1", 15, DacPair.CH12)


def test_single_sequence_defaults_to_zero_after() -> None:
    sequence = DacSequence.single(np.zeros(8), np.zeros(8))
    assert sequence.mode is PlayMode.ZERO_AFTER
