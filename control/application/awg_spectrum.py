"""Configured MMCS-AWG to spectrum-analyzer experiment."""

from __future__ import annotations

from typing import Annotated, TypeVar

import numpy as np
from pydantic import Field, StringConstraints

from control.config import ControlConfig, MmcsDeviceConfig, SpectrumAnalyzerDeviceConfig
from control.core.exceptions import AcquisitionError, ConfigurationError, ValidationError
from control.core.model import FrozenModel
from control.domain.mmcs import (
    DacChannel,
    GeneratedSingleTone,
    MmcsProgram,
    SingleToneSpec,
    build_cyclic_dac_program,
    generate_single_tone,
)
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace
from control.factory import InstrumentFactory

from .mmcs import MmcsExecutor
from .sweeps import SpectrumAnalyzerController


T = TypeVar("T")
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _default(value: T | None, fallback: T) -> T:
    return fallback if value is None else value


class MmcsAwgSpectrumSpec(FrozenModel):
    mmcs_name: NonEmptyString
    spectrum_analyzer_name: NonEmptyString
    master_box: NonEmptyString
    dac_board_id: NonEmptyString
    dac_channel: DacChannel
    tone_frequency_hz: float
    tone_amplitude: float
    tone_phase_rad: float
    spectrum_span_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    points: int | None = None
    resolution_bandwidth_hz: float | None = None
    input_attenuation_db: float | None = None
    acquisition_timeout_s: float | None = None
    minimum_waveform_samples: int | None = None
    period_ns: int | None = None
    start_trigger_ns: int | None = None
    safety_margin_s: float | None = None

class ResolvedAwgSpectrum(FrozenModel):
    spec: MmcsAwgSpectrumSpec
    tone: GeneratedSingleTone
    program: MmcsProgram
    spectrum_config: SpectrumSweepConfig
    acquisition_timeout_s: float
    safety_margin_s: float

    @property
    def output_safety_window_s(self) -> float:
        return self.acquisition_timeout_s + self.safety_margin_s


class AwgSpectrumResult(FrozenModel):
    trace: SpectrumTrace
    actual_frequency_hz: float


def acquire_spectrum_while_mmcs_runs(
    executor: MmcsExecutor,
    analyzer: SpectrumAnalyzerController,
    *,
    program: MmcsProgram,
    spectrum_config: SpectrumSweepConfig,
    spectrum_timeout_s: float,
) -> SpectrumTrace:
    executor.prepare(program)
    executor.start()
    primary_error: BaseException | None = None
    try:
        return analyzer.acquire(spectrum_config, timeout_s=spectrum_timeout_s)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            executor.stop()
        except Exception as stop_exc:
            if primary_error is not None:
                primary_error.add_note(f"Stopping MMCS output also failed: {stop_exc}")
            else:
                raise AcquisitionError("Spectrum acquired but stopping MMCS output failed") from stop_exc


class MmcsAwgSpectrumExperiment:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config

    def resolve(self, spec: MmcsAwgSpectrumSpec) -> ResolvedAwgSpectrum:
        mmcs = self.config.require(spec.mmcs_name, MmcsDeviceConfig)
        self.config.require(spec.spectrum_analyzer_name, SpectrumAnalyzerDeviceConfig)
        if spec.master_box not in mmcs.boxes:
            raise ConfigurationError(f"MMCS master box {spec.master_box!r} is not configured")
        board = mmcs.require_dac_board(spec.dac_board_id)
        spectrum_defaults = self.config.defaults.spectrum_sweep
        awg_defaults = self.config.defaults.mmcs_awg

        timeout = _default(spec.acquisition_timeout_s, spectrum_defaults.acquisition_timeout_s)
        margin = _default(spec.safety_margin_s, awg_defaults.safety_margin_s)
        if not np.isfinite([timeout, margin]).all() or timeout <= 0 or margin <= 0:
            raise ValidationError("acquisition timeout and safety margin must be finite and positive")

        tone = generate_single_tone(
            SingleToneSpec(
                sample_rate_hz=board.sample_rate_hz,
                frequency_hz=spec.tone_frequency_hz,
                amplitude=spec.tone_amplitude,
                phase_rad=spec.tone_phase_rad,
                minimum_samples=_default(
                    spec.minimum_waveform_samples,
                    awg_defaults.minimum_waveform_samples,
                ),
            )
        )
        program = build_cyclic_dac_program(
            tone.waveform,
            board_id=spec.dac_board_id,
            channel=spec.dac_channel,
            master_box=spec.master_box,
            run_duration_s=timeout + margin,
            period_ns=_default(spec.period_ns, awg_defaults.period_ns),
            start_trigger_ns=_default(spec.start_trigger_ns, awg_defaults.start_trigger_ns),
        )
        rbw = _default(
            spec.resolution_bandwidth_hz,
            spec.spectrum_span_hz * spectrum_defaults.rbw_span_ratio,
        )
        spectrum_config = SpectrumSweepConfig.from_center_span(
            center_hz=tone.actual_frequency_hz,
            span_hz=spec.spectrum_span_hz,
            points=_default(spec.points, spectrum_defaults.points),
            resolution_bandwidth_hz=rbw,
            input_attenuation_db=_default(
                spec.input_attenuation_db,
                spectrum_defaults.input_attenuation_db,
            ),
        )
        return ResolvedAwgSpectrum(
            spec=spec,
            tone=tone,
            program=program,
            spectrum_config=spectrum_config,
            acquisition_timeout_s=float(timeout),
            safety_margin_s=float(margin),
        )

    def acquire(self, spec: MmcsAwgSpectrumSpec) -> AwgSpectrumResult:
        resolved = self.resolve(spec)
        factory = InstrumentFactory(self.config)
        cleanup = self.config.defaults.mmcs_execution.cleanup_timeout_s
        with factory.create_mmcs(spec.mmcs_name) as mmcs_driver:
            with factory.create_spectrum_analyzer(spec.spectrum_analyzer_name) as analyzer_driver:
                trace = acquire_spectrum_while_mmcs_runs(
                    MmcsExecutor(mmcs_driver, cleanup_timeout_s=cleanup),
                    SpectrumAnalyzerController(analyzer_driver),
                    program=resolved.program,
                    spectrum_config=resolved.spectrum_config,
                    spectrum_timeout_s=resolved.acquisition_timeout_s,
                )
        return AwgSpectrumResult(
            trace=trace,
            actual_frequency_hz=resolved.tone.actual_frequency_hz,
        )
