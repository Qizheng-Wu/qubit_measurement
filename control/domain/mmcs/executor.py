"""Reliable upload and execution workflow for MMCS programs."""

from __future__ import annotations

import time

import numpy as np

from control.core.exceptions import InstrumentStateError, ProtocolError, ValidationError
from control.driver.mmcs import MmcsHardwareDriver

from .model import MmcsProgram, PreparedMmcsProgram, RunningMmcsProgram
from .result import MmcsIqResult, MmcsResult
from .validator import validate_program


class MmcsExecutor:
    def __init__(self, driver: MmcsHardwareDriver, *, cleanup_timeout_s: float = 5.0) -> None:
        if cleanup_timeout_s <= 0:
            raise ValidationError("cleanup_timeout_s must be positive")
        self.driver = driver
        self.cleanup_timeout_s = cleanup_timeout_s
        self._running: RunningMmcsProgram | None = None

    def _require_connected(self) -> None:
        if not self.driver.is_connected:
            raise InstrumentStateError("MMCS driver must be connected")

    def _cleanup_after_error(self, exc: BaseException, master_box: str) -> None:
        try:
            self.driver.stop_all(master_box, timeout_s=self.cleanup_timeout_s)
        except Exception as cleanup_exc:
            exc.add_note(f"MMCS stop after failure also failed: {cleanup_exc}")
        try:
            self.driver.clear_all_trigger_ram()
        except Exception as cleanup_exc:
            exc.add_note(f"MMCS trigger cleanup after failure also failed: {cleanup_exc}")

    def prepare(self, program: MmcsProgram) -> PreparedMmcsProgram:
        validate_program(program)
        self._require_connected()
        if self._running is not None:
            raise InstrumentStateError("Cannot prepare while an MMCS program is running")
        try:
            self.driver.stop_all(program.master_box, timeout_s=self.cleanup_timeout_s)
            self.driver.clear_all_trigger_ram()
            for adc in program.adc_programs:
                self.driver.clear_adc_data(adc.board_id)
            for dac in program.dac_programs:
                playlist = [
                    {"trigger": int(entry.trigger), "wave_idx": entry.waveform_index}
                    for entry in dac.playlist
                ]
                self.driver.upload_dac_waveforms(
                    board_id=dac.board_id,
                    channel=dac.channel.value,
                    play_mode=dac.play_mode.value,
                    waveforms=[waveform.samples for waveform in dac.waveforms],
                    playlist=playlist,
                )
                self.driver.configure_dac_triggers(
                    board_id=dac.board_id,
                    timestamps_ns=[event.time_ns for event in dac.triggers],
                    commands=[int(event.command) for event in dac.triggers],
                )
            for adc in program.adc_programs:
                self.driver.configure_adc_sampling(
                    board_id=adc.board_id,
                    sample_length=adc.sample_length,
                    repetitions=program.repetitions,
                )
                for weights in adc.demodulations:
                    self.driver.upload_demodulation_weights(
                        board_id=adc.board_id,
                        channel=weights.channel,
                        i_weights=weights.i,
                        q_weights=weights.q,
                    )
                self.driver.configure_adc_triggers(
                    board_id=adc.board_id,
                    timestamps_ns=[event.time_ns for event in adc.triggers],
                )
        except BaseException as exc:
            self._cleanup_after_error(exc, program.master_box)
            raise
        return PreparedMmcsProgram(
            program=program,
            fingerprint=program.fingerprint(),
            connection_generation=self.driver.generation,
        )

    def _validate_prepared(self, prepared: PreparedMmcsProgram) -> None:
        self._require_connected()
        if prepared.connection_generation != self.driver.generation:
            raise InstrumentStateError("Prepared MMCS program is invalid after reconnect")
        if prepared.fingerprint != prepared.program.fingerprint():
            raise InstrumentStateError("Prepared MMCS program fingerprint no longer matches")

    def _require_running(self, running: RunningMmcsProgram) -> None:
        self._require_connected()
        if self._running is not running:
            raise InstrumentStateError("MMCS program is not active on this executor")

    def start(self, prepared: PreparedMmcsProgram) -> RunningMmcsProgram:
        """Start a prepared program without waiting for it to finish."""

        self._validate_prepared(prepared)
        if self._running is not None:
            raise InstrumentStateError("An MMCS program is already running")
        program = prepared.program
        started = time.perf_counter()
        try:
            for adc in program.adc_programs:
                self.driver.clear_adc_data(adc.board_id)
            self.driver.configure_level1_trigger(
                repetitions=program.repetitions, period_ns=program.period_ns
            )
            self.driver.start(program.master_box)
        except BaseException as exc:
            self._cleanup_after_error(exc, program.master_box)
            raise
        running = RunningMmcsProgram(prepared=prepared, started_at_s=started)
        self._running = running
        return running

    def wait(self, running: RunningMmcsProgram, *, timeout_s: float) -> MmcsResult:
        """Wait for a running program and collect all configured ADC results."""

        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        self._require_running(running)
        prepared = running.prepared
        program = prepared.program
        try:
            self.driver.wait(program.master_box, timeout_s=timeout_s)
            results: dict[str, MmcsIqResult] = {}
            for adc in program.adc_programs:
                raw = self.driver.fetch_iq(adc.board_id)
                if not isinstance(raw, (tuple, list)) or len(raw) != 5:
                    raise ProtocolError(f"MMCS ADC {adc.board_id!r} returned malformed IQ data")
                arrays = tuple(np.asarray(value) for value in raw)
                if any(array.ndim != 2 or array.shape[0] != 12 for array in arrays):
                    shapes = [array.shape for array in arrays]
                    raise ProtocolError(
                        f"MMCS ADC {adc.board_id!r} IQ arrays must have 12 rows, got {shapes}"
                    )
                results[adc.board_id] = MmcsIqResult(*arrays)
        except BaseException as exc:
            self._cleanup_after_error(exc, program.master_box)
            raise
        finally:
            self._running = None
        return MmcsResult(
            iq_by_adc=results,
            period_ns=program.period_ns,
            repetitions=program.repetitions,
            elapsed_s=time.perf_counter() - running.started_at_s,
            program_fingerprint=prepared.fingerprint,
        )

    def stop(self, running: RunningMmcsProgram) -> None:
        """Stop an active program without waiting on the vendor socket."""

        self._require_running(running)
        self.driver.stop_all(
            running.prepared.program.master_box,
            timeout_s=self.cleanup_timeout_s,
        )
        self._running = None

    def run(self, prepared: PreparedMmcsProgram, *, timeout_s: float) -> MmcsResult:
        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        return self.wait(self.start(prepared), timeout_s=timeout_s)

    def execute(self, program: MmcsProgram, *, timeout_s: float) -> MmcsResult:
        return self.run(self.prepare(program), timeout_s=timeout_s)
