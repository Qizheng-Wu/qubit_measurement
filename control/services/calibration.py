"""Automatic two-stage IQ mixer calibration orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize

from control.core.exceptions import ValidationError
from control.db import IqCalibrationRepository
from control.domain.calibration import IqAutoCalibrationResult, IqAutoCalibrationSpec
from control.domain.mmcs import IqCalibration, IqToneSpec
from control.domain.power import ScalarPowerMeasurementConfig, ScalarPowerResult

from .mmcs import MmcsService
from .program import build_iq_upconversion_program
from .spectrum import ScalarPowerSession, SpectrumAnalyzerService
from .waveform import generate_iq_tone


class _PatienceConverged(Exception):
    pass


@dataclass
class _StageState:
    best_calibration: IqCalibration
    best_power_dbm: float
    evaluations: int = 0
    callbacks_without_improvement: int = 0
    callback_best_dbm: float = np.inf
    termination_reason: str = ""


class IqAutoCalibrationService:
    def __init__(
        self,
        mmcs: MmcsService,
        spectrum: SpectrumAnalyzerService,
        repository: IqCalibrationRepository,
    ) -> None:
        self.mmcs = mmcs
        self.spectrum = spectrum
        self.repository = repository
        self._global_sequence = 0
        self._stage_sequences: dict[str, int] = {}

    @staticmethod
    def _scalar_config(
        spec: IqAutoCalibrationSpec, frequency_hz: float
    ) -> ScalarPowerMeasurementConfig:
        return ScalarPowerMeasurementConfig(
            frequency_hz=frequency_hz,
            span_hz=spec.spectrum_span_hz,
            points=spec.spectrum_points,
            resolution_bandwidth_hz=spec.resolution_bandwidth_hz,
            input_attenuation_db=spec.input_attenuation_db,
        )

    def _record_evaluation(
        self,
        *,
        run_id: int,
        stage: str,
        calibration: IqCalibration,
        frequency_hz: float,
        readings_dbm: tuple[float, ...],
        objective_dbm: float,
        elapsed_s: float,
    ) -> None:
        self._global_sequence += 1
        stage_sequence = self._stage_sequences.get(stage, 0) + 1
        self._stage_sequences[stage] = stage_sequence
        self.repository.append_evaluation(
            run_id,
            stage=stage,
            global_sequence=self._global_sequence,
            stage_sequence=stage_sequence,
            q_over_i_gain=calibration.q_over_i_gain,
            i_offset=calibration.i_offset,
            q_offset=calibration.q_offset,
            q_phase_correction_rad=calibration.q_phase_correction_rad,
            measurement_frequency_hz=frequency_hz,
            readings_dbm=list(readings_dbm),
            objective_dbm=objective_dbm,
            elapsed_s=elapsed_s,
        )

    def _measure_candidate(
        self,
        *,
        run_id: int,
        stage: str,
        spec: IqAutoCalibrationSpec,
        calibration: IqCalibration,
        meter: ScalarPowerSession,
    ) -> float:
        started = time.perf_counter()
        try:
            tone = generate_iq_tone(
                IqToneSpec(
                    sample_rate_hz=spec.sample_rate_hz,
                    if_frequency_hz=spec.if_frequency_hz,
                    amplitude=spec.amplitude,
                    phase_rad=0.0,
                    minimum_samples=spec.minimum_samples,
                    sideband=spec.sideband,
                    calibration=calibration,
                )
            )
        except ValidationError:
            elapsed = time.perf_counter() - started
            self._record_evaluation(
                run_id=run_id,
                stage=stage,
                calibration=calibration,
                frequency_hz=meter.config.frequency_hz,
                readings_dbm=(),
                objective_dbm=1e9,
                elapsed_s=elapsed,
            )
            return 1e9
        run_duration_s = (
            spec.measurement_timeout_s * spec.measurement_repetitions + 2.0
        )
        program = build_iq_upconversion_program(
            tone,
            board_id=spec.board_id,
            master_box=spec.master_box,
            run_duration_s=run_duration_s,
            period_ns=spec.period_ns,
            start_trigger_ns=spec.start_trigger_ns,
        )
        with self.mmcs.running(program):
            measurement = meter.measure(
                repetitions=spec.measurement_repetitions,
                timeout_s=spec.measurement_timeout_s,
            )
        self._record_evaluation(
            run_id=run_id,
            stage=stage,
            calibration=calibration,
            frequency_hz=meter.config.frequency_hz,
            readings_dbm=measurement.readings_dbm,
            objective_dbm=measurement.power_dbm,
            elapsed_s=time.perf_counter() - started,
        )
        return measurement.power_dbm

    def _measure_at_frequency(
        self,
        *,
        run_id: int,
        stage: str,
        spec: IqAutoCalibrationSpec,
        calibration: IqCalibration,
        frequency_hz: float,
    ) -> float:
        with self.spectrum.scalar_power_session(
            self._scalar_config(spec, frequency_hz)
        ) as meter:
            return self._measure_candidate(
                run_id=run_id,
                stage=stage,
                spec=spec,
                calibration=calibration,
                meter=meter,
            )

    def _optimize_stage(
        self,
        *,
        run_id: int,
        stage: str,
        spec: IqAutoCalibrationSpec,
        starting: IqCalibration,
        frequency_hz: float,
        x0: np.ndarray,
        bounds: tuple[tuple[float, float], tuple[float, float]],
        build_calibration: Callable[[np.ndarray], IqCalibration],
    ) -> _StageState:
        state = _StageState(starting, np.inf)

        with self.spectrum.scalar_power_session(
            self._scalar_config(spec, frequency_hz)
        ) as meter:
            def objective(values: np.ndarray) -> float:
                calibration = build_calibration(values)
                power = self._measure_candidate(
                    run_id=run_id,
                    stage=stage,
                    spec=spec,
                    calibration=calibration,
                    meter=meter,
                )
                state.evaluations += 1
                if power < state.best_power_dbm:
                    state.best_power_dbm = power
                    state.best_calibration = calibration
                return power

            def callback(_values: np.ndarray) -> None:
                improvement = state.callback_best_dbm - state.best_power_dbm
                if improvement >= spec.improvement_tolerance_db:
                    state.callbacks_without_improvement = 0
                else:
                    state.callbacks_without_improvement += 1
                state.callback_best_dbm = state.best_power_dbm
                if state.callbacks_without_improvement >= spec.patience_iterations:
                    raise _PatienceConverged

            try:
                result = minimize(
                    objective,
                    x0,
                    method="Powell",
                    bounds=bounds,
                    callback=callback,
                    options={
                        "maxfev": spec.max_evaluations_per_stage,
                        "xtol": 1e-4,
                        "ftol": 1e-4,
                    },
                )
            except _PatienceConverged:
                state.termination_reason = "improvement tolerance reached"
            else:
                state.termination_reason = str(result.message)
        return state

    @staticmethod
    def _result_values(calibration: IqCalibration) -> dict[str, float]:
        return {
            "best_q_over_i_gain": calibration.q_over_i_gain,
            "best_i_offset": calibration.i_offset,
            "best_q_offset": calibration.q_offset,
            "best_q_phase_correction_rad": calibration.q_phase_correction_rad,
        }

    def calibrate(self, spec: IqAutoCalibrationSpec) -> IqAutoCalibrationResult:
        self.repository.initialize()
        self._global_sequence = 0
        self._stage_sequences.clear()
        initial = spec.initial_calibration
        spectrum_id = self.spectrum.driver.identity.raw
        mmcs_version = repr(self.mmcs.check_status())
        run_id = self.repository.create_run(
            signal_path=spec.signal_path,
            board_id=spec.board_id,
            lo_frequency_hz=spec.lo_frequency_hz,
            if_frequency_hz=spec.if_frequency_hz,
            sideband=spec.sideband.value,
            amplitude=spec.amplitude,
            sample_rate_hz=spec.sample_rate_hz,
            initial_q_over_i_gain=initial.q_over_i_gain,
            initial_i_offset=initial.i_offset,
            initial_q_offset=initial.q_offset,
            initial_q_phase_correction_rad=initial.q_phase_correction_rad,
            spectrum_analyzer_id=spectrum_id,
            mmcs_version=mmcs_version,
        )
        best = initial
        offset_state: _StageState | None = None
        imbalance_state: _StageState | None = None
        try:
            initial_lo = self._measure_at_frequency(
                run_id=run_id, stage="baseline", spec=spec,
                calibration=initial, frequency_hz=spec.lo_frequency_hz,
            )
            initial_target = self._measure_at_frequency(
                run_id=run_id, stage="baseline", spec=spec,
                calibration=initial, frequency_hz=spec.target_frequency_hz,
            )
            initial_image = self._measure_at_frequency(
                run_id=run_id, stage="baseline", spec=spec,
                calibration=initial, frequency_hz=spec.image_frequency_hz,
            )

            offset_state = self._optimize_stage(
                run_id=run_id,
                stage="offset",
                spec=spec,
                starting=initial,
                frequency_hz=spec.lo_frequency_hz,
                x0=np.array([initial.i_offset, initial.q_offset]),
                bounds=spec.offset_bounds,
                build_calibration=lambda values: initial.model_copy(
                    update={"i_offset": float(values[0]), "q_offset": float(values[1])}
                ),
            )
            best = offset_state.best_calibration
            fixed_offset = best
            imbalance_state = self._optimize_stage(
                run_id=run_id,
                stage="imbalance",
                spec=spec,
                starting=fixed_offset,
                frequency_hz=spec.image_frequency_hz,
                x0=np.array([
                    fixed_offset.q_over_i_gain,
                    fixed_offset.q_phase_correction_rad,
                ]),
                bounds=spec.imbalance_bounds,
                build_calibration=lambda values: fixed_offset.model_copy(
                    update={
                        "q_over_i_gain": float(values[0]),
                        "q_phase_correction_rad": float(values[1]),
                    }
                ),
            )
            best = imbalance_state.best_calibration
            final_lo = self._measure_at_frequency(
                run_id=run_id, stage="validation", spec=spec,
                calibration=best, frequency_hz=spec.lo_frequency_hz,
            )
            final_target = self._measure_at_frequency(
                run_id=run_id, stage="validation", spec=spec,
                calibration=best, frequency_hz=spec.target_frequency_hz,
            )
            final_image = self._measure_at_frequency(
                run_id=run_id, stage="validation", spec=spec,
                calibration=best, frequency_hz=spec.image_frequency_hz,
            )
            termination = (
                f"offset: {offset_state.termination_reason}; "
                f"imbalance: {imbalance_state.termination_reason}"
            )
            converged = all(
                "maximum" not in state.termination_reason.lower()
                for state in (offset_state, imbalance_state)
            )
            self.repository.complete_run(
                run_id,
                **self._result_values(best),
                initial_lo_dbm=initial_lo,
                initial_target_dbm=initial_target,
                initial_image_dbm=initial_image,
                final_lo_dbm=final_lo,
                final_target_dbm=final_target,
                final_image_dbm=final_image,
                lo_improvement_db=initial_lo - final_lo,
                image_improvement_db=initial_image - final_image,
                image_rejection_db=final_target - final_image,
                offset_evaluations=offset_state.evaluations,
                imbalance_evaluations=imbalance_state.evaluations,
                optimizer_converged=converged,
                termination_reason=termination,
            )
            return IqAutoCalibrationResult(
                run_id=run_id,
                calibration=best,
                initial_lo_dbm=initial_lo,
                final_lo_dbm=final_lo,
                initial_target_dbm=initial_target,
                final_target_dbm=final_target,
                initial_image_dbm=initial_image,
                final_image_dbm=final_image,
                image_rejection_db=final_target - final_image,
                optimizer_converged=converged,
                termination_reason=termination,
                offset_evaluations=offset_state.evaluations,
                imbalance_evaluations=imbalance_state.evaluations,
            )
        except (KeyboardInterrupt, SystemExit) as exc:
            self.repository.interrupt_run(
                run_id,
                error_message=str(exc) or type(exc).__name__,
                **self._result_values(best),
                offset_evaluations=offset_state.evaluations if offset_state else 0,
                imbalance_evaluations=imbalance_state.evaluations if imbalance_state else 0,
            )
            raise
        except Exception as exc:
            self.repository.fail_run(
                run_id,
                error_message=str(exc),
                **self._result_values(best),
                offset_evaluations=offset_state.evaluations if offset_state else 0,
                imbalance_evaluations=imbalance_state.evaluations if imbalance_state else 0,
            )
            raise
