"""Display the spectrum of a single tone from one configured MMCS DAC board."""

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

from control.application import (
    MmcsExecutor,
    SpectrumAnalyzerController,
    acquire_spectrum_while_mmcs_runs,
)
from control.config import (
    MmcsDeviceConfig,
    SpectrumAnalyzerDeviceConfig,
    load_control_config,
)
from control.domain.mmcs import (
    DacChannel,
    SingleToneSpec,
    build_cyclic_dac_program,
    generate_single_tone,
)
from control.domain.sweep import SpectrumSweepConfig
from control.factory import InstrumentFactory

CONFIG_PATH = Path("config/instruments.local.toml")
RUN_HARDWARE = False


@dataclass(frozen=True)
class ExperimentSpec:
    mmcs_name: str
    spectrum_analyzer_name: str
    master_box: str
    dac_board_id: str
    dac_channel: DacChannel
    tone_frequency_hz: float
    tone_amplitude: float
    tone_phase_rad: float
    spectrum_span_hz: float


EXPERIMENT = ExperimentSpec(
    mmcs_name="mmcs",
    spectrum_analyzer_name="spectrum",
    master_box="box1",
    dac_board_id="da_box1pcie1ch12",
    dac_channel=DacChannel.I,
    tone_frequency_hz=20e6,
    tone_amplitude=0.02,
    tone_phase_rad=0.0,
    spectrum_span_hz=10e6,
)


def _plot(trace, actual_frequency_hz: float) -> None:
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
    config = load_control_config(CONFIG_PATH)
    mmcs_config = config.require(EXPERIMENT.mmcs_name, MmcsDeviceConfig)
    config.require(EXPERIMENT.spectrum_analyzer_name, SpectrumAnalyzerDeviceConfig)
    board = mmcs_config.require_dac_board(EXPERIMENT.dac_board_id)
    spectrum_defaults = config.defaults.spectrum_sweep
    awg_defaults = config.defaults.mmcs_awg

    tone = generate_single_tone(
        SingleToneSpec(
            sample_rate_hz=board.sample_rate_hz,
            frequency_hz=EXPERIMENT.tone_frequency_hz,
            amplitude=EXPERIMENT.tone_amplitude,
            phase_rad=EXPERIMENT.tone_phase_rad,
            minimum_samples=awg_defaults.minimum_waveform_samples,
        )
    )
    timeout = spectrum_defaults.acquisition_timeout_s
    safety_window = timeout + awg_defaults.safety_margin_s
    program = build_cyclic_dac_program(
        tone.waveform,
        board_id=EXPERIMENT.dac_board_id,
        channel=EXPERIMENT.dac_channel,
        master_box=EXPERIMENT.master_box,
        run_duration_s=safety_window,
        period_ns=awg_defaults.period_ns,
        start_trigger_ns=awg_defaults.start_trigger_ns,
    )
    spectrum_config = SpectrumSweepConfig.from_center_span(
        center_hz=tone.actual_frequency_hz,
        span_hz=EXPERIMENT.spectrum_span_hz,
        points=spectrum_defaults.points,
        resolution_bandwidth_hz=(
            EXPERIMENT.spectrum_span_hz * spectrum_defaults.rbw_span_ratio
        ),
        input_attenuation_db=spectrum_defaults.input_attenuation_db,
    )

    print(
        f"board={EXPERIMENT.dac_board_id}, channel={EXPERIMENT.dac_channel.value}, "
        f"sample_rate={tone.spec.sample_rate_hz / 1e9:.6f} GHz, "
        f"requested={EXPERIMENT.tone_frequency_hz / 1e6:.6f} MHz, "
        f"actual={tone.actual_frequency_hz / 1e6:.6f} MHz, "
        f"samples={tone.waveform.samples.size}, period={program.period_ns} ns, "
        f"RBW={spectrum_config.resolution_bandwidth_hz / 1e3:.3f} kHz, "
        f"attenuation={spectrum_config.input_attenuation_db:.1f} dB, "
        f"timeout={timeout:.1f} s, safety_window={safety_window:.1f} s"
    )
    if not RUN_HARDWARE:
        print("Dry run only. Set RUN_HARDWARE=True after checking cabling and attenuation.")
        return 0

    factory = InstrumentFactory(config)
    cleanup_timeout = config.defaults.mmcs_execution.cleanup_timeout_s
    with factory.create_mmcs(EXPERIMENT.mmcs_name) as mmcs_driver:
        with factory.create_spectrum_analyzer(EXPERIMENT.spectrum_analyzer_name) as analyzer_driver:
            trace = acquire_spectrum_while_mmcs_runs(
                MmcsExecutor(mmcs_driver, cleanup_timeout_s=cleanup_timeout),
                SpectrumAnalyzerController(analyzer_driver),
                program=program,
                spectrum_config=spectrum_config,
                spectrum_timeout_s=timeout,
            )
    _plot(trace, tone.actual_frequency_hz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
