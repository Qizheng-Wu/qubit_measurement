"""Drive one MMCS DAC into a spectrum analyzer and display the trace.

Connect the selected DAC output through suitable attenuation before enabling
hardware access.  Edit the constants below for the local setup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import matplotlib.pyplot as plt

from control import InstrumentFactory, SpectrumAnalyzerController, load_control_config
from control.config import MmcsDeviceConfig
from control.core.exceptions import AcquisitionError
from control.domain.mmcs import (
    DacChannel,
    MmcsExecutor,
    MmcsProgram,
    PreparedMmcsProgram,
    RunningMmcsProgram,
    SingleToneSpec,
    build_cyclic_dac_program,
    generate_single_tone,
)
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace

# Connection and hardware selection.
CONFIG_PATH = Path("config/instruments.local.toml")
MMCS_NAME = "mmcs"
SPECTRUM_ANALYZER_NAME = "spectrum"
DAC_BOARD_ID = "da_box1pcie1ch12"
DAC_CHANNEL = DacChannel.I

# This must be filled from the actual MMCS DAC specification before use.
DAC_SAMPLE_RATE_HZ: float | None = None

# Conservative signal and acquisition defaults.
TONE_FREQUENCY_HZ = 20e6
TONE_AMPLITUDE = 0.02
TONE_PHASE_RAD = 0.0
MINIMUM_WAVEFORM_SAMPLES = 800
MMCS_PERIOD_NS = 1_000_000
SPECTRUM_SPAN_HZ = 10e6
SPECTRUM_POINTS = 501
SPECTRUM_RBW_HZ = 100e3
SPECTRUM_INPUT_ATTENUATION_DB = 20.0
SPECTRUM_TIMEOUT_S = 30.0
OUTPUT_SAFETY_WINDOW_S = SPECTRUM_TIMEOUT_S + 5.0

# Leave False until cabling, attenuation, DAC channel, and sample rate are checked.
RUN_HARDWARE = False


class MmcsExecutorLike(Protocol):
    def prepare(self, program: MmcsProgram) -> PreparedMmcsProgram: ...

    def start(self, prepared: PreparedMmcsProgram) -> RunningMmcsProgram: ...

    def stop(self, running: RunningMmcsProgram) -> None: ...


class SpectrumAnalyzerLike(Protocol):
    def acquire(
        self, config: SpectrumSweepConfig, *, timeout_s: float
    ) -> SpectrumTrace: ...


def acquire_spectrum_while_mmcs_runs(
    executor: MmcsExecutorLike,
    analyzer: SpectrumAnalyzerLike,
    *,
    program: MmcsProgram,
    spectrum_config: SpectrumSweepConfig,
    spectrum_timeout_s: float,
) -> SpectrumTrace:
    """Acquire a spectrum between non-blocking MMCS start and stop calls."""

    prepared = executor.prepare(program)
    running = executor.start(prepared)
    primary_error: BaseException | None = None
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
                raise AcquisitionError(
                    "Spectrum acquired but stopping MMCS output failed"
                ) from stop_exc


def _plot_trace(trace: SpectrumTrace, *, actual_frequency_hz: float) -> None:
    plt.plot(trace.frequency_hz / 1e6, trace.power_dbm)
    plt.axvline(
        actual_frequency_hz / 1e6,
        color="tab:red",
        linestyle="--",
        label="generated tone",
    )
    plt.xlabel("Frequency (MHz)")
    plt.ylabel("Power (dBm)")
    plt.title("MMCS AWG spectrum")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.show()


def main() -> int:
    if DAC_SAMPLE_RATE_HZ is None:
        print("Set DAC_SAMPLE_RATE_HZ to the actual hardware sample rate before running.")
        return 2

    tone = generate_single_tone(
        SingleToneSpec(
            sample_rate_hz=DAC_SAMPLE_RATE_HZ,
            frequency_hz=TONE_FREQUENCY_HZ,
            amplitude=TONE_AMPLITUDE,
            phase_rad=TONE_PHASE_RAD,
            minimum_samples=MINIMUM_WAVEFORM_SAMPLES,
        )
    )
    config = load_control_config(CONFIG_PATH)
    mmcs_config = config.require(MMCS_NAME, MmcsDeviceConfig)
    program = build_cyclic_dac_program(
        tone.waveform,
        board_id=DAC_BOARD_ID,
        channel=DAC_CHANNEL,
        master_box=mmcs_config.master_box,
        run_duration_s=OUTPUT_SAFETY_WINDOW_S,
        period_ns=MMCS_PERIOD_NS,
    )
    spectrum_config = SpectrumSweepConfig.from_center_span(
        center_hz=tone.actual_frequency_hz,
        span_hz=SPECTRUM_SPAN_HZ,
        points=SPECTRUM_POINTS,
        resolution_bandwidth_hz=SPECTRUM_RBW_HZ,
        input_attenuation_db=SPECTRUM_INPUT_ATTENUATION_DB,
    )

    print(
        f"Prepared {tone.waveform.samples.size} samples; "
        f"requested={tone.spec.frequency_hz / 1e6:.6f} MHz, "
        f"actual={tone.actual_frequency_hz / 1e6:.6f} MHz, "
        f"safety window={OUTPUT_SAFETY_WINDOW_S:.1f} s"
    )
    if not RUN_HARDWARE:
        print("Dry run only. Set RUN_HARDWARE=True after checking cabling and attenuation.")
        return 0

    factory = InstrumentFactory(config)
    with factory.create_mmcs(MMCS_NAME) as mmcs_driver:
        with factory.create_spectrum_analyzer(SPECTRUM_ANALYZER_NAME) as analyzer_driver:
            trace = acquire_spectrum_while_mmcs_runs(
                MmcsExecutor(
                    mmcs_driver,
                    cleanup_timeout_s=mmcs_config.cleanup_timeout_s,
                ),
                SpectrumAnalyzerController(analyzer_driver),
                program=program,
                spectrum_config=spectrum_config,
                spectrum_timeout_s=SPECTRUM_TIMEOUT_S,
            )

    _plot_trace(trace, actual_frequency_hz=tone.actual_frequency_hz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
