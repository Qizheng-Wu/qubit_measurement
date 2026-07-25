"""Reusable MMCS program construction."""

from __future__ import annotations

import math

import numpy as np

from control.core.exceptions import ValidationError
from control.domain.mmcs.iq_tone import GeneratedIqTone
from control.domain.mmcs.model import (
    DacBoardProgram,
    DacChannel,
    DacChannelProgram,
    DacPlayMode,
    DacWaveform,
    MmcsProgram,
    PlaylistEntry,
    TriggerCommand,
    TriggerEvent,
)


def _cyclic_timing(
    *, run_duration_s: float, period_ns: int, start_trigger_ns: int
) -> tuple[int, tuple[TriggerEvent, ...]]:
    if not np.isfinite(run_duration_s) or run_duration_s <= 0:
        raise ValidationError("run_duration_s must be finite and positive")
    if isinstance(period_ns, bool) or not isinstance(period_ns, int) or period_ns <= 0:
        raise ValidationError("period_ns must be a positive integer")
    stop_trigger_ns = period_ns - 4
    if stop_trigger_ns <= start_trigger_ns:
        raise ValidationError("period_ns must leave room for START and STOP triggers")
    repetitions = max(1, math.ceil(run_duration_s / (period_ns * 1e-9)))
    triggers = (
        TriggerEvent(time_ns=start_trigger_ns, command=TriggerCommand.START),
        TriggerEvent(time_ns=stop_trigger_ns, command=TriggerCommand.STOP),
    )
    return repetitions, triggers


def _cyclic_channel(channel: DacChannel, waveform: DacWaveform) -> DacChannelProgram:
    return DacChannelProgram(
        channel=channel,
        waveforms=(waveform,),
        playlist=(PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),),
        play_mode=DacPlayMode.CYCLE,
    )


def _build_cyclic_iq_program(
    *,
    i_waveform: DacWaveform,
    q_waveform: DacWaveform,
    board_id: str,
    master_box: str,
    run_duration_s: float,
    period_ns: int,
    start_trigger_ns: int,
) -> MmcsProgram:
    repetitions, triggers = _cyclic_timing(
        run_duration_s=run_duration_s,
        period_ns=period_ns,
        start_trigger_ns=start_trigger_ns,
    )
    return MmcsProgram(
        master_box=master_box,
        period_ns=period_ns,
        repetitions=repetitions,
        dac_boards=(
            DacBoardProgram(
                board_id=board_id,
                triggers=triggers,
                channels=(
                    _cyclic_channel(DacChannel.I, i_waveform),
                    _cyclic_channel(DacChannel.Q, q_waveform),
                ),
            ),
        ),
    )


def build_cyclic_dac_program(
    waveform: DacWaveform,
    *,
    board_id: str,
    channel: DacChannel,
    master_box: str,
    run_duration_s: float,
    period_ns: int,
    start_trigger_ns: int,
) -> MmcsProgram:
    """Build a finite sequence that cycles one waveform during each period."""

    if not isinstance(channel, DacChannel):
        raise ValidationError("channel must be a DacChannel")
    zero = DacWaveform(samples=np.zeros_like(waveform.samples))
    return _build_cyclic_iq_program(
        i_waveform=waveform if channel is DacChannel.I else zero,
        q_waveform=waveform if channel is DacChannel.Q else zero,
        board_id=board_id,
        master_box=master_box,
        run_duration_s=run_duration_s,
        period_ns=period_ns,
        start_trigger_ns=start_trigger_ns,
    )


def build_iq_upconversion_program(
    tone: GeneratedIqTone,
    *,
    board_id: str,
    master_box: str,
    run_duration_s: float,
    period_ns: int,
    start_trigger_ns: int,
) -> MmcsProgram:
    """Build a cyclic board program that owns and synchronizes both IQ channels."""

    return _build_cyclic_iq_program(
        i_waveform=tone.i_waveform,
        q_waveform=tone.q_waveform,
        board_id=board_id,
        master_box=master_box,
        run_duration_s=run_duration_s,
        period_ns=period_ns,
        start_trigger_ns=start_trigger_ns,
    )
