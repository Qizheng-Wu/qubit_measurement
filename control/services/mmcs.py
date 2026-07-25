"""MMCS program loading and execution service."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

import numpy as np

from control.core.exceptions import InstrumentStateError, ProtocolError, ValidationError
from control.domain.mmcs.model import MmcsProgram
from control.domain.mmcs.result import MmcsIqResult, MmcsResult
from control.driver.mmcs import MmcsHardwareDriver

from .base import BaseInstrumentService


class MmcsRun:
    def __init__(self, service: "MmcsService", program: MmcsProgram) -> None:
        self._service = service
        self._program = program
        self._result: MmcsResult | None = None

    @property
    def completed(self) -> bool:
        return self._result is not None

    def result(self, *, timeout_s: float) -> MmcsResult:
        if self._result is not None:
            return self._result
        self._service._require_active_run(self)
        self._result = self._service._finish(self._program, timeout_s=timeout_s)
        return self._result


class MmcsService(BaseInstrumentService):
    def __init__(self, driver: MmcsHardwareDriver, *, cleanup_timeout_s: float) -> None:
        if cleanup_timeout_s <= 0:
            raise ValidationError("cleanup_timeout_s must be positive")
        super().__init__(driver)
        self.cleanup_timeout_s = float(cleanup_timeout_s)
        self._hardware_running = False
        self._started_at_s = 0.0

    @property
    def driver(self) -> MmcsHardwareDriver:
        return self._driver

    def check_status(self) -> Any:
        """Query every configured MMCS backplane and board for its FPGA version."""

        self._require_connected()
        return self.driver.identify()

    def _cleanup_after_error(self, exc: BaseException, master_box: str) -> None:
        try:
            self._stop_and_clear(master_box)
        except Exception as cleanup_exc:
            exc.add_note(f"MMCS cleanup after failure also failed: {cleanup_exc}")
        self._hardware_running = False

    def _stop_and_clear(self, master_box: str) -> None:
        stop_error: BaseException | None = None
        try:
            self.driver.stop_all(master_box, timeout_s=self.cleanup_timeout_s)
        except BaseException as exc:
            stop_error = exc
        try:
            self.driver.clear_all_trigger_ram()
        except BaseException as clear_exc:
            if stop_error is not None:
                stop_error.add_note(f"Clearing MMCS trigger RAM also failed: {clear_exc}")
            else:
                raise
        if stop_error is not None:
            raise stop_error

    def _prepare(self, program: MmcsProgram) -> None:
        try:
            self._stop_and_clear(program.master_box)
            for adc in program.adc_programs:
                self.driver.clear_adc_data(adc.board_id)
            for board in program.dac_boards:
                self.driver.clear_dac_waveforms(board.board_id)
                for channel in sorted(board.channels, key=lambda item: item.channel.value):
                    self.driver.upload_dac_waveforms(
                        board_id=board.board_id,
                        channel=channel.channel.value,
                        play_mode=channel.play_mode.value,
                        waveforms=[waveform.samples for waveform in channel.waveforms],
                        playlist=[
                            {"trigger": int(entry.trigger), "wave_idx": entry.waveform_index}
                            for entry in channel.playlist
                        ],
                    )
            for board in program.dac_boards:
                self.driver.configure_dac_triggers(
                    board_id=board.board_id,
                    timestamps_ns=[event.time_ns for event in board.triggers],
                    commands=[int(event.command) for event in board.triggers],
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

    def _start(self, program: MmcsProgram) -> None:
        self._started_at_s = time.perf_counter()
        try:
            for adc in program.adc_programs:
                self.driver.clear_adc_data(adc.board_id)
            self.driver.configure_level1_trigger(
                repetitions=program.repetitions,
                period_ns=program.period_ns,
            )
            self.driver.start(program.master_box)
        except BaseException as exc:
            self._cleanup_after_error(exc, program.master_box)
            raise
        self._hardware_running = True

    def _finish(self, program: MmcsProgram, *, timeout_s: float) -> MmcsResult:
        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        try:
            self.driver.wait(program.master_box, timeout_s=timeout_s)
            results: dict[str, MmcsIqResult] = {}
            for adc in program.adc_programs:
                raw = self.driver.fetch_iq(adc.board_id)
                if not isinstance(raw, (tuple, list)) or len(raw) != 5:
                    raise ProtocolError(
                        f"MMCS ADC {adc.board_id!r} returned malformed IQ data"
                    )
                arrays = tuple(np.asarray(value) for value in raw)
                if any(array.ndim != 2 or array.shape[0] != 12 for array in arrays):
                    shapes = [array.shape for array in arrays]
                    raise ProtocolError(
                        f"MMCS ADC {adc.board_id!r} IQ arrays must have 12 rows, got {shapes}"
                    )
                results[adc.board_id] = MmcsIqResult(
                    i_sum=arrays[0],
                    q_sum=arrays[1],
                    i_average=arrays[2],
                    q_average=arrays[3],
                    state_flags=arrays[4],
                )
            self._stop(program)
        except BaseException as exc:
            self._cleanup_after_error(exc, program.master_box)
            raise
        return MmcsResult(
            iq_by_adc=results,
            period_ns=program.period_ns,
            repetitions=program.repetitions,
            elapsed_s=time.perf_counter() - self._started_at_s,
            program_fingerprint=program.fingerprint(),
        )

    def _stop(self, program: MmcsProgram) -> None:
        try:
            self._stop_and_clear(program.master_box)
        finally:
            self._hardware_running = False

    @contextmanager
    def running(self, program: MmcsProgram) -> Iterator[MmcsRun]:
        self._require_connected()
        if self._active_run is not None:
            raise InstrumentStateError("Instrument service is already running")
        self._prepare(program)
        self._start(program)
        run = MmcsRun(self, program)
        self._activate_run(run)
        primary_error: BaseException | None = None
        try:
            yield run
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            try:
                if self._hardware_running:
                    self._stop(program)
            except Exception as cleanup_exc:
                if primary_error is not None:
                    primary_error.add_note(f"Stopping MMCS also failed: {cleanup_exc}")
                else:
                    raise
            finally:
                self._deactivate_run(run)
