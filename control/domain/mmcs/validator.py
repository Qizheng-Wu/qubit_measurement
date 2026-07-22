"""Pre-flight validation for complete MMCS programs."""

from __future__ import annotations

import numpy as np

from control.core.exceptions import ValidationError

from .model import DacChannel, DacPlayMode, MmcsProgram, TriggerCommand


def _validate_triggers(triggers, *, period_ns: int, adc: bool) -> None:
    if not triggers:
        raise ValidationError("Every MMCS board program requires at least one trigger")
    if any(not isinstance(event.command, TriggerCommand) for event in triggers):
        raise ValidationError("Trigger commands must be TriggerCommand values")
    times = [event.time_ns for event in triggers]
    if any(not isinstance(value, int) for value in times):
        raise ValidationError("Trigger times must be integers")
    if any(value <= 0 or value % 4 for value in times):
        raise ValidationError("Trigger times must be positive multiples of 4 ns")
    if any(current <= previous for previous, current in zip(times, times[1:])):
        raise ValidationError("Trigger times must be strictly increasing")
    if times[-1] >= period_ns:
        raise ValidationError("Trigger times must be earlier than period_ns")
    if adc and any(event.command is not TriggerCommand.START for event in triggers):
        raise ValidationError("ADC trigger events only support START")


def validate_program(program: MmcsProgram) -> None:
    if not program.master_box:
        raise ValidationError("master_box cannot be empty")
    if not isinstance(program.period_ns, int) or program.period_ns <= 0 or program.period_ns % 4:
        raise ValidationError("period_ns must be a positive integer multiple of 4")
    if not isinstance(program.repetitions, int) or program.repetitions < 1:
        raise ValidationError("repetitions must be an integer >= 1")
    if not program.dac_programs and not program.adc_programs:
        raise ValidationError("MMCS program cannot be empty")

    channel_keys: set[tuple[str, str]] = set()
    for dac in program.dac_programs:
        if not isinstance(dac.channel, DacChannel) or not isinstance(dac.play_mode, DacPlayMode):
            raise ValidationError("DAC channel and play mode must use their enum types")
        key = (dac.board_id, dac.channel.value)
        if not dac.board_id or key in channel_keys:
            raise ValidationError(f"Duplicate or empty DAC channel: {key!r}")
        channel_keys.add(key)
        if not dac.waveforms or not dac.playlist:
            raise ValidationError(f"DAC {key!r} requires waveforms and a playlist")
        for waveform in dac.waveforms:
            values = waveform.samples
            if values.ndim != 1 or values.size == 0 or values.size % 8:
                raise ValidationError("DAC waveforms must be non-empty 1-D arrays aligned to 8 samples")
            if not np.all(np.isfinite(values)) or np.any(np.abs(values) > 1):
                raise ValidationError("DAC waveform samples must be finite and within [-1, 1]")
        for entry in dac.playlist:
            if not isinstance(entry.trigger, TriggerCommand):
                raise ValidationError("Playlist triggers must be TriggerCommand values")
            if entry.trigger is not TriggerCommand.START:
                raise ValidationError("MMCS v1 playlists only support START entries")
            if not 0 <= entry.waveform_index < len(dac.waveforms):
                raise ValidationError("Playlist waveform index is out of range")
        _validate_triggers(dac.triggers, period_ns=program.period_ns, adc=False)
        if dac.play_mode is DacPlayMode.CYCLE and not any(
            event.command is TriggerCommand.STOP for event in dac.triggers
        ):
            raise ValidationError("Cyclic DAC playback requires a STOP trigger")

    adc_ids: set[str] = set()
    for adc in program.adc_programs:
        if not adc.board_id or adc.board_id in adc_ids:
            raise ValidationError(f"Duplicate or empty ADC board: {adc.board_id!r}")
        adc_ids.add(adc.board_id)
        if not isinstance(adc.sample_length, int) or not 4 <= adc.sample_length <= 8000:
            raise ValidationError("ADC sample_length must be an integer in [4, 8000]")
        if adc.sample_length % 4:
            raise ValidationError("ADC sample_length must be aligned to 4 samples")
        channels: set[int] = set()
        for weights in adc.demodulations:
            if weights.channel not in range(12) or weights.channel in channels:
                raise ValidationError("Demodulation channels must be unique integers in [0, 11]")
            channels.add(weights.channel)
            if weights.i.ndim != 1 or weights.q.ndim != 1:
                raise ValidationError("Demodulation weights must be 1-D")
            if weights.i.size != adc.sample_length or weights.q.size != adc.sample_length:
                raise ValidationError("Demodulation weight length must equal ADC sample_length")
            if not np.all(np.isfinite(weights.i)) or not np.all(np.isfinite(weights.q)):
                raise ValidationError("Demodulation weights must be finite")
            if np.any(np.abs(weights.i) > 1) or np.any(np.abs(weights.q) > 1):
                raise ValidationError("Demodulation weights must be within [-1, 1]")
        _validate_triggers(adc.triggers, period_ns=program.period_ns, adc=True)
