"""Reusable MMCS program construction."""

from __future__ import annotations

import math

import numpy as np

from control.core.exceptions import ValidationError
from control.domain.mmcs.model import (
    DacChannel,
    DacPlayMode,
    DacProgram,
    DacWaveform,
    MmcsProgram,
    PlaylistEntry,
    TriggerCommand,
    TriggerEvent,
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

    if not np.isfinite(run_duration_s) or run_duration_s <= 0:
        raise ValidationError("run_duration_s must be finite and positive")
    if isinstance(period_ns, bool) or not isinstance(period_ns, int) or period_ns <= 0:
        raise ValidationError("period_ns must be a positive integer")
    stop_trigger_ns = period_ns - 4
    if stop_trigger_ns <= start_trigger_ns:
        raise ValidationError("period_ns must leave room for START and STOP triggers")

    repetitions = max(1, math.ceil(run_duration_s / (period_ns * 1e-9)))
    return MmcsProgram(
        master_box=master_box,
        period_ns=period_ns,
        repetitions=repetitions,
        dac_programs=(
            DacProgram(
                board_id=board_id,
                channel=channel,
                waveforms=(waveform,),
                playlist=(
                    PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),
                ),
                play_mode=DacPlayMode.CYCLE,
                triggers=(
                    TriggerEvent(time_ns=start_trigger_ns, command=TriggerCommand.START),
                    TriggerEvent(time_ns=stop_trigger_ns, command=TriggerCommand.STOP),
                ),
            ),
        ),
    )
