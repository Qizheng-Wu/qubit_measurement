"""Display the spectrum of a single tone from one configured MMCS DAC board."""

from pathlib import Path

import matplotlib.pyplot as plt

from control.application import MmcsAwgSpectrumExperiment, MmcsAwgSpectrumSpec
from control.config import load_control_config
from control.domain.mmcs import DacChannel

CONFIG_PATH = Path("config/instruments.local.toml")
RUN_HARDWARE = False

EXPERIMENT = MmcsAwgSpectrumSpec(
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


def _plot(result) -> None:
    trace = result.trace
    plt.plot(trace.frequency_hz / 1e6, trace.power_dbm)
    plt.axvline(
        result.actual_frequency_hz / 1e6,
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
    experiment = MmcsAwgSpectrumExperiment(config)
    resolved = experiment.resolve(EXPERIMENT)
    print(
        f"board={EXPERIMENT.dac_board_id}, channel={EXPERIMENT.dac_channel.value}, "
        f"sample_rate={resolved.tone.spec.sample_rate_hz / 1e9:.6f} GHz, "
        f"requested={EXPERIMENT.tone_frequency_hz / 1e6:.6f} MHz, "
        f"actual={resolved.tone.actual_frequency_hz / 1e6:.6f} MHz, "
        f"samples={resolved.tone.waveform.samples.size}, "
        f"period={resolved.program.period_ns} ns, "
        f"RBW={resolved.spectrum_config.resolution_bandwidth_hz / 1e3:.3f} kHz, "
        f"attenuation={resolved.spectrum_config.input_attenuation_db:.1f} dB, "
        f"timeout={resolved.acquisition_timeout_s:.1f} s, "
        f"safety_window={resolved.output_safety_window_s:.1f} s"
    )
    if not RUN_HARDWARE:
        print("Dry run only. Set RUN_HARDWARE=True after checking cabling and attenuation.")
        return 0
    _plot(experiment.acquire(EXPERIMENT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
