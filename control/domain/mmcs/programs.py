"""Convenience builders for common MMCS output programs."""

from __future__ import annotations

import math

import numpy as np

from control.core.exceptions import ValidationError

from .model import (
    DacChannel,
    DacPlayMode,
    DacProgram,
    DacWaveform,
    MmcsProgram,
    PlaylistEntry,
    TriggerCommand,
    TriggerEvent,
)
from .validator import validate_program


def build_cyclic_dac_program(
    waveform: DacWaveform,
    *,
    board_id: str,
    channel: DacChannel,
    master_box: str,
    run_duration_s: float,
    period_ns: int = 1_000_000,
    start_trigger_ns: int = 40,
) -> MmcsProgram:
    """Build a finite sequence that cycles one waveform during each period."""

    if not np.isfinite(run_duration_s) or run_duration_s <= 0:
        raise ValidationError("run_duration_s must be finite and positive")
    if isinstance(period_ns, bool) or not isinstance(period_ns, int) or period_ns % 4:
        raise ValidationError("period_ns must be an integer multiple of 4 ns")
    if (
        isinstance(start_trigger_ns, bool)
        or not isinstance(start_trigger_ns, int)
        or start_trigger_ns <= 0
        or start_trigger_ns % 4
    ):
        raise ValidationError("start_trigger_ns must be a positive integer multiple of 4 ns")
    stop_trigger_ns = period_ns - 4
    if stop_trigger_ns <= start_trigger_ns:
        raise ValidationError("period_ns must leave room for START and STOP triggers")

    repetitions = max(1, math.ceil(run_duration_s / (period_ns * 1e-9)))
    program = MmcsProgram(
        master_box=master_box,
        period_ns=period_ns,
        repetitions=repetitions,
        dac_programs=(
            DacProgram(
                board_id=board_id,
                channel=channel,
                waveforms=(waveform,),
                playlist=(PlaylistEntry(0),),
                play_mode=DacPlayMode.CYCLE,
                triggers=(
                    TriggerEvent(start_trigger_ns, TriggerCommand.START),
                    TriggerEvent(stop_trigger_ns, TriggerCommand.STOP),
                ),
            ),
        ),
    )
    validate_program(program)
    return program
