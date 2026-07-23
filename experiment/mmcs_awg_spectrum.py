"""Display the spectrum of a single tone from one configured MMCS DAC board."""

from dataclasses import dataclass
from pathlib import Path

from control.config import (
    ControlConfig,
    MmcsDeviceConfig,
    SpectrumAnalyzerDeviceConfig,
    load_control_config,
)
from control.domain.mmcs import (
    DacChannel,
    GeneratedSingleTone,
    MmcsProgram,
    SingleToneSpec,
)
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace
from control.factory import InstrumentFactory
from control.services import (
    MmcsService,
    SpectrumAnalyzerService,
    build_cyclic_dac_program,
    generate_single_tone,
)

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


@dataclass(frozen=True)
class ExperimentPlan:
    tone: GeneratedSingleTone
    mmcs_program: MmcsProgram
    spectrum_config: SpectrumSweepConfig
    spectrum_timeout_s: float
    safety_window_s: float


def resolve_experiment(
    spec: ExperimentSpec,
    config: ControlConfig,
) -> ExperimentPlan:
    mmcs_config = config.require(spec.mmcs_name, MmcsDeviceConfig)
    config.require(spec.spectrum_analyzer_name, SpectrumAnalyzerDeviceConfig)
    board = mmcs_config.require_dac_board(spec.dac_board_id)
    spectrum_defaults = config.defaults.spectrum_sweep
    awg_defaults = config.defaults.mmcs_awg

    tone = generate_single_tone(
        SingleToneSpec(
            sample_rate_hz=board.sample_rate_hz,
            frequency_hz=spec.tone_frequency_hz,
            amplitude=spec.tone_amplitude,
            phase_rad=spec.tone_phase_rad,
            minimum_samples=awg_defaults.minimum_waveform_samples,
        )
    )
    timeout = spectrum_defaults.acquisition_timeout_s
    safety_window = timeout + awg_defaults.safety_margin_s
    program = build_cyclic_dac_program(
        tone.waveform,
        board_id=spec.dac_board_id,
        channel=spec.dac_channel,
        master_box=spec.master_box,
        run_duration_s=safety_window,
        period_ns=awg_defaults.period_ns,
        start_trigger_ns=awg_defaults.start_trigger_ns,
    )
    spectrum_config = SpectrumSweepConfig.from_center_span(
        center_hz=tone.actual_frequency_hz,
        span_hz=spec.spectrum_span_hz,
        points=spectrum_defaults.points,
        resolution_bandwidth_hz=(
            spec.spectrum_span_hz * spectrum_defaults.rbw_span_ratio
        ),
        input_attenuation_db=spectrum_defaults.input_attenuation_db,
    )
    return ExperimentPlan(
        tone=tone,
        mmcs_program=program,
        spectrum_config=spectrum_config,
        spectrum_timeout_s=timeout,
        safety_window_s=safety_window,
    )


def print_plan(spec: ExperimentSpec, plan: ExperimentPlan) -> None:
    tone = plan.tone
    spectrum_config = plan.spectrum_config
    print(
        f"board={spec.dac_board_id}, channel={spec.dac_channel.value}, "
        f"sample_rate={tone.spec.sample_rate_hz / 1e9:.6f} GHz, "
        f"requested={spec.tone_frequency_hz / 1e6:.6f} MHz, "
        f"actual={tone.actual_frequency_hz / 1e6:.6f} MHz, "
        f"samples={tone.waveform.samples.size}, period={plan.mmcs_program.period_ns} ns, "
        f"RBW={spectrum_config.resolution_bandwidth_hz / 1e3:.3f} kHz, "
        f"attenuation={spectrum_config.input_attenuation_db:.1f} dB, "
        f"timeout={plan.spectrum_timeout_s:.1f} s, "
        f"safety_window={plan.safety_window_s:.1f} s"
    )


def run_experiment(
    mmcs: MmcsService,
    spectrum: SpectrumAnalyzerService,
    plan: ExperimentPlan,
) -> SpectrumTrace:
    with mmcs.connected(), spectrum.connected():
        with mmcs.running(plan.mmcs_program):
            with spectrum.running(plan.spectrum_config) as sweep:
                return sweep.result(timeout_s=plan.spectrum_timeout_s)


def plot_result(trace: SpectrumTrace, plan: ExperimentPlan) -> None:
    import matplotlib.pyplot as plt

    plt.plot(trace.frequency_hz / 1e6, trace.power_dbm)
    plt.axvline(
        plan.tone.actual_frequency_hz / 1e6,
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
    plan = resolve_experiment(EXPERIMENT, config)
    print_plan(EXPERIMENT, plan)
    if not RUN_HARDWARE:
        print("Dry run only. Set RUN_HARDWARE=True after checking cabling and attenuation.")
        return 0

    factory = InstrumentFactory(config)
    trace = run_experiment(
        factory.create_mmcs_service(EXPERIMENT.mmcs_name),
        factory.create_spectrum_analyzer_service(EXPERIMENT.spectrum_analyzer_name),
        plan,
    )
    plot_result(trace, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
