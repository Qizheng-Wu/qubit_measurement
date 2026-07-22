"""Configured MMCS-AWG to spectrum-analyzer smoke experiment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import numpy as np

from control.config import ControlConfig, MmcsDeviceConfig, SpectrumAnalyzerDeviceConfig
from control.core.exceptions import AcquisitionError, ConfigurationError, ValidationError
from control.domain.mmcs import (
    DacChannel, GeneratedSingleTone, MmcsExecutor, MmcsProgram,
    PreparedMmcsProgram, RunningMmcsProgram, SingleToneSpec,
    build_cyclic_dac_program, generate_single_tone,
)
from control.domain.sweep import SpectrumAnalyzerController, SpectrumSweepConfig
from control.domain.trace import SpectrumTrace
from control.factory import InstrumentFactory


@dataclass(frozen=True, slots=True, kw_only=True)
class MmcsAwgSpectrumSpec:
    mmcs_name: str
    spectrum_analyzer_name: str
    master_box: str
    dac_board_id: str
    dac_channel: DacChannel
    tone_frequency_hz: float
    tone_amplitude: float
    tone_phase_rad: float
    spectrum_span_hz: float

    def __post_init__(self) -> None:
        for name in ("mmcs_name", "spectrum_analyzer_name", "master_box", "dac_board_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{name} must be a non-empty string")
        if not isinstance(self.dac_channel, DacChannel):
            raise ValidationError("dac_channel must be a DacChannel")
        if not np.isfinite(self.spectrum_span_hz) or self.spectrum_span_hz <= 0:
            raise ValidationError("spectrum_span_hz must be finite and positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class AwgSpectrumEngineeringOverrides:
    points: int | None = None
    resolution_bandwidth_hz: float | None = None
    input_attenuation_db: float | None = None
    acquisition_timeout_s: float | None = None
    minimum_waveform_samples: int | None = None
    period_ns: int | None = None
    start_trigger_ns: int | None = None
    safety_margin_s: float | None = None


@dataclass(frozen=True, slots=True)
class ResolvedAwgSpectrum:
    spec: MmcsAwgSpectrumSpec
    tone: GeneratedSingleTone
    program: MmcsProgram
    spectrum_config: SpectrumSweepConfig
    acquisition_timeout_s: float
    safety_margin_s: float

    @property
    def output_safety_window_s(self) -> float:
        return self.acquisition_timeout_s + self.safety_margin_s


@dataclass(frozen=True, slots=True)
class AwgSpectrumResult:
    trace: SpectrumTrace
    actual_frequency_hz: float


class MmcsExecutorLike(Protocol):
    def prepare(self, program: MmcsProgram) -> PreparedMmcsProgram: ...
    def start(self, prepared: PreparedMmcsProgram) -> RunningMmcsProgram: ...
    def stop(self, running: RunningMmcsProgram) -> None: ...


class SpectrumAnalyzerLike(Protocol):
    def acquire(self, config: SpectrumSweepConfig, *, timeout_s: float) -> SpectrumTrace: ...


def acquire_spectrum_while_mmcs_runs(
    executor: MmcsExecutorLike,
    analyzer: SpectrumAnalyzerLike,
    *,
    program: MmcsProgram,
    spectrum_config: SpectrumSweepConfig,
    spectrum_timeout_s: float,
) -> SpectrumTrace:
    prepared = executor.prepare(program)
    running = executor.start(prepared)
    primary_error = None
    try:
        return analyzer.acquire(spectrum_config, timeout_s=spectrum_timeout_s)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            executor.stop(running)
        except Exception as stop_exc:
            if primary_error is not None:
                primary_error.add_note(f"Stopping MMCS output also failed: {stop_exc}")
            else:
                raise AcquisitionError("Spectrum acquired but stopping MMCS output failed") from stop_exc


class MmcsAwgSpectrumExperiment:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config

    def resolve(
        self,
        spec: MmcsAwgSpectrumSpec,
        overrides: AwgSpectrumEngineeringOverrides | None = None,
    ) -> ResolvedAwgSpectrum:
        mmcs = self.config.require(spec.mmcs_name, MmcsDeviceConfig)
        self.config.require(spec.spectrum_analyzer_name, SpectrumAnalyzerDeviceConfig)
        if spec.master_box not in mmcs.boxes:
            raise ConfigurationError(f"MMCS master box {spec.master_box!r} is not configured")
        board = mmcs.require_dac_board(spec.dac_board_id)
        override = overrides or AwgSpectrumEngineeringOverrides()
        spectrum_defaults = self.config.defaults.spectrum_sweep
        awg_defaults = self.config.defaults.mmcs_awg
        minimum = awg_defaults.minimum_waveform_samples if override.minimum_waveform_samples is None else override.minimum_waveform_samples
        tone = generate_single_tone(SingleToneSpec(
            sample_rate_hz=board.sample_rate_hz,
            frequency_hz=spec.tone_frequency_hz,
            amplitude=spec.tone_amplitude,
            phase_rad=spec.tone_phase_rad,
            minimum_samples=minimum,
        ))
        timeout = spectrum_defaults.acquisition_timeout_s if override.acquisition_timeout_s is None else override.acquisition_timeout_s
        margin = awg_defaults.safety_margin_s if override.safety_margin_s is None else override.safety_margin_s
        if not np.isfinite([timeout, margin]).all() or timeout <= 0 or margin <= 0:
            raise ValidationError("acquisition timeout and safety margin must be finite and positive")
        period = awg_defaults.period_ns if override.period_ns is None else override.period_ns
        start = awg_defaults.start_trigger_ns if override.start_trigger_ns is None else override.start_trigger_ns
        program = build_cyclic_dac_program(
            tone.waveform, board_id=spec.dac_board_id, channel=spec.dac_channel,
            master_box=spec.master_box, run_duration_s=timeout + margin,
            period_ns=period, start_trigger_ns=start,
        )
        rbw = spec.spectrum_span_hz * spectrum_defaults.rbw_span_ratio if override.resolution_bandwidth_hz is None else override.resolution_bandwidth_hz
        spectrum_config = SpectrumSweepConfig.from_center_span(
            center_hz=tone.actual_frequency_hz, span_hz=spec.spectrum_span_hz,
            points=spectrum_defaults.points if override.points is None else override.points,
            resolution_bandwidth_hz=rbw,
            input_attenuation_db=spectrum_defaults.input_attenuation_db if override.input_attenuation_db is None else override.input_attenuation_db,
        )
        return ResolvedAwgSpectrum(spec, tone, program, spectrum_config, float(timeout), float(margin))

    def acquire(
        self,
        spec: MmcsAwgSpectrumSpec,
        overrides: AwgSpectrumEngineeringOverrides | None = None,
    ) -> AwgSpectrumResult:
        resolved = self.resolve(spec, overrides)
        factory = InstrumentFactory(self.config)
        cleanup = self.config.defaults.mmcs_execution.cleanup_timeout_s
        with factory.create_mmcs(spec.mmcs_name) as mmcs_driver:
            with factory.create_spectrum_analyzer(spec.spectrum_analyzer_name) as analyzer_driver:
                trace = acquire_spectrum_while_mmcs_runs(
                    MmcsExecutor(mmcs_driver, cleanup_timeout_s=cleanup),
                    SpectrumAnalyzerController(analyzer_driver),
                    program=resolved.program, spectrum_config=resolved.spectrum_config,
                    spectrum_timeout_s=resolved.acquisition_timeout_s,
                )
        return AwgSpectrumResult(trace, resolved.tone.actual_frequency_hz)
