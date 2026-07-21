from __future__ import annotations

import csv
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# ---------------------------------------------------------------------------
# Paths and hardware mapping
# ---------------------------------------------------------------------------

MMCS_SOURCE_DIR = Path(r"D:\User\liuzc\lab4\src")
DATA_FOLDER = Path(
    r"F:\ExpData\20260712_cooldown.dir\20260712_sampleB2.dir"
)

MMCS_IP = "192.168.4.8"
BOX_NAME = "box1"

QUBIT_XY_DAC_NAME = "da_box1pcie3ch12"
READOUT_DAC_NAME = "da_box1pcie2ch12"
READOUT_ADC_NAME = "ad_box1pcie1ch12"
ADC_FREQ_CHANNEL = 0


# ---------------------------------------------------------------------------
# Preliminary frequencies from the 2026-07-06 data
# ---------------------------------------------------------------------------

QUBIT_FREQ_HZ = 3.53556e9
RESONATOR_FREQ_HZ = 7.07115e9

# Instrument VISA resources copied from the working two-tone program.
VNA_RESOURCE = "USB0::0x2A8D::0x5A01::MY47100891::0::INSTR"
ANRITSU_RESOURCE = "GPIB0::5::INSTR"

QUBIT_LO_HZ = 3.40000e9
READOUT_LO_HZ = 7.00000e9

# Upper-sideband convention: RF = LO + IF.
QUBIT_IF_HZ = QUBIT_FREQ_HZ - QUBIT_LO_HZ
READOUT_IF_HZ = RESONATOR_FREQ_HZ - READOUT_LO_HZ

# These are LO-port setpoints, not powers at the chip.
QUBIT_LO_POWER_DBM = 10.0
READOUT_LO_POWER_DBM = 10.0


# ---------------------------------------------------------------------------
# Conservative first-pass Rabi configuration.  A longer drive pulse lowers the
# peak amplitude needed for a visible rotation compared with the earlier
# 40-ns/0.50 trial settings.
# ---------------------------------------------------------------------------

SAFETY_PROFILE = "conservative_100ns_amp0_to_0p30"
DRIVE_AMPLITUDES = np.linspace(0.0, 0.049, 50)
DRIVE_PULSE_NS = 100.0
DRIVE_READOUT_GAP_NS = 20.0

READOUT_AMPLITUDE = 0.05
READOUT_LENGTH_NS = 1000.0
ADC_SAMPLE_LENGTH = 1000

REPS = 3000
CYCLE_PERIOD_NS = 70_000

# Existing configuration/Runner timing values.
BASE_TRIGGER_NS = 40
XY_TRIGGER_DELAY_NS = 16
READOUT_TRIGGER_DELAY_NS = 16
ADC_TRIGGER_DELAY_NS = 180

# If the expected upper sideband is absent, verify the spectrum before changing
# these.  Change only one of them at a time.
# The vendor example uses I=sin and Q=cos when the DAC board's built-in mixer
# is used.  Both slot-2 and slot-3 outputs in this setup use that mixer.
SWAP_IQ = True
Q_SIGN = +1

# Physical-chain notes saved as metadata.  These are not used to calculate an
# absolute chip power because mixer conversion loss is not calibrated yet.
INPUT_LINE_ATTENUATION_MIN_DB = 60.0
INPUT_LINE_ATTENUATION_MAX_DB = 70.0
RETURN_CHAIN_GAIN_DB = 50.0

REQUIRE_RUN_CONFIRMATION = True


DAC_SAMPLE_RATE_HZ = 2.0e9
ADC_SAMPLE_RATE_HZ = 1.0e9


def load_dependencies():
    """Import the MMCS driver and the available LogFolder implementation."""

    if str(MMCS_SOURCE_DIR) not in sys.path:
        sys.path.insert(0, str(MMCS_SOURCE_DIR))

    from MMCSDriver.mmcs_driver import MmcsDriver
    from lab4.instr.keysight_vna import VNA
    from lab4.instr.MG36221A_LO import LocalOsci as LO

    try:
        from logqbit.logfolder import LogFolder

        logfolder_backend = "logqbit.logfolder"
    except ImportError:
        from labrad_servers.logfolder import LogFolder

        logfolder_backend = "labrad_servers.logfolder"

    return MmcsDriver, VNA, LO, LogFolder, logfolder_backend


def identify_instrument(instrument) -> str:
    """Return *IDN? when supported, without making it a hard requirement."""

    try:
        return str(instrument.query("*IDN?")).strip()
    except Exception as first_error:
        # Some instrument wrappers expose only the underlying VISA resource.
        visa_resource = getattr(instrument, "instr", None)
        if visa_resource is not None and hasattr(visa_resource, "query"):
            try:
                return str(visa_resource.query("*IDN?")).strip()
            except Exception:
                pass
        return f"IDN unavailable: {first_error!r}"


def set_output_enabled(instrument, enabled: bool) -> None:
    """Enable/disable RF output using the driver API or SCPI fallback."""

    if hasattr(instrument, "set_output_state"):
        instrument.set_output_state(bool(enabled))
        return

    command = "OUTP ON" if enabled else "OUTP OFF"
    if hasattr(instrument, "write"):
        instrument.write(command)
        return

    raise AttributeError(
        f"{type(instrument).__name__} has no output-state method"
    )


def configure_vna_as_readout_lo(vna) -> None:
    """Configure the Keysight VNA as a zero-span 7-GHz CW LO."""

    # Prefer direct setters so the VNA does not perform an unnecessary read.
    if hasattr(vna, "set_center_Hz") and hasattr(vna, "set_span_Hz"):
        vna.set_center_Hz(READOUT_LO_HZ)
        vna.set_span_Hz(0)
        vna.set_power_dBm(READOUT_LO_POWER_DBM)
        set_output_enabled(vna, True)
    else:
        # This exact high-level method is proven by the old two-tone code.
        set_output_enabled(vna, True)
        vna.sweep_center_span(
            center_Hz=READOUT_LO_HZ,
            span_Hz=0,
            npts=51,
            bandwidth_Hz=100,
            power_dBm=READOUT_LO_POWER_DBM,
        )


def configure_anritsu_as_qubit_lo(qubit_lo) -> None:
    """Configure the MG36221A source as the Qubit IQ-mixer LO."""

    qubit_lo.set_freq_Hz(QUBIT_LO_HZ)
    qubit_lo.set_power_dBm(QUBIT_LO_POWER_DBM)
    set_output_enabled(qubit_lo, True)


def optional_readback(instrument, method_name: str):
    method = getattr(instrument, method_name, None)
    if method is None:
        return None
    try:
        return method()
    except Exception:
        return None


def get_output_enabled(instrument):
    """Read RF state while tolerating the drivers' inconsistent parsers.

    Some VNA wrappers compare ``OUTP?`` only with ``"ON"``, while the
    E5071C normally answers ``"1"``.  Query the underlying VISA object first
    and normalize both forms before falling back to the wrapper method.
    """

    visa = getattr(instrument, "instr", None)
    query_targets = [visa, instrument]
    for target in query_targets:
        if target is None or not hasattr(target, "query"):
            continue
        try:
            raw = str(target.query("OUTP?")).strip().upper()
        except Exception:
            continue
        if raw in {"1", "1.0", "ON", "TRUE"}:
            return True
        if raw in {"0", "0.0", "OFF", "FALSE"}:
            return False

    state = optional_readback(instrument, "get_output_state")
    if isinstance(state, (bool, np.bool_)):
        return bool(state)
    if isinstance(state, (int, float, np.integer, np.floating)):
        return bool(state)
    if isinstance(state, str):
        normalized = state.strip().upper()
        if normalized in {"1", "1.0", "ON", "TRUE"}:
            return True
        if normalized in {"0", "0.0", "OFF", "FALSE"}:
            return False
    return None


def round_up(value: float, multiple: int) -> int:
    return int(np.ceil(value / multiple) * multiple)


def make_iq_wave(
    if_freq_hz: float,
    amplitude: float,
    length_ns: float,
    envelope: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate normalized 2-GS/s IQ data with length divisible by eight."""

    sample_count = max(
        8,
        round_up(length_ns * DAC_SAMPLE_RATE_HZ / 1e9, 8),
    )
    time_s = np.arange(sample_count) / DAC_SAMPLE_RATE_HZ

    if envelope == "hann":
        shape = np.hanning(sample_count)
    elif envelope == "rect":
        shape = np.ones(sample_count)
    else:
        raise ValueError(f"Unknown envelope: {envelope}")

    phase = 2.0 * np.pi * if_freq_hz * time_s
    i_wave = amplitude * shape * np.cos(phase)
    q_wave = Q_SIGN * amplitude * shape * np.sin(phase)

    if SWAP_IQ:
        i_wave, q_wave = q_wave, i_wave

    return np.asarray(i_wave, dtype=float), np.asarray(q_wave, dtype=float)


def validate_config() -> None:
    errors: list[str] = []

    if not MMCS_SOURCE_DIR.exists():
        errors.append(f"MMCS source folder does not exist: {MMCS_SOURCE_DIR}")
    if abs(QUBIT_IF_HZ) >= DAC_SAMPLE_RATE_HZ / 2:
        errors.append("abs(QUBIT_IF_HZ) must be below 1 GHz")
    if abs(READOUT_IF_HZ) >= ADC_SAMPLE_RATE_HZ / 2:
        errors.append("abs(READOUT_IF_HZ) must be below 500 MHz")
    if not (0.0 < READOUT_AMPLITUDE <= 1.0):
        errors.append("READOUT_AMPLITUDE must be in (0, 1]")
    if np.any(DRIVE_AMPLITUDES < 0) or np.any(DRIVE_AMPLITUDES > 1):
        errors.append("Every drive amplitude must be in [0, 1]")
    if ADC_SAMPLE_LENGTH <= 0 or ADC_SAMPLE_LENGTH > 8000:
        errors.append("ADC_SAMPLE_LENGTH must be in [1, 8000]")
    if ADC_SAMPLE_LENGTH % 4:
        errors.append("ADC_SAMPLE_LENGTH must be divisible by 4")
    if CYCLE_PERIOD_NS % 4:
        errors.append("CYCLE_PERIOD_NS must be divisible by 4 ns")
    if REPS <= 0:
        errors.append("REPS must be positive")
    if Q_SIGN not in (-1, +1):
        errors.append("Q_SIGN must be -1 or +1")

    if errors:
        raise ValueError("\n".join(errors))


def stop_mmcs(mmcs) -> None:
    mmcs.sys_stop_all_borad(master_box_name=BOX_NAME)
    mmcs.sys_clear_all_level2_trigger_ram()


def set_single_iq_wave(mmcs, dac_name: str, i_wave, q_wave) -> None:
    result_i = mmcs.da_set_single_waveform(
        name=dac_name,
        iq_channel_select="i",
        wave=np.asarray(i_wave, dtype=float),
        play_mode="end_with_zero",
    )
    result_q = mmcs.da_set_single_waveform(
        name=dac_name,
        iq_channel_select="q",
        wave=np.asarray(q_wave, dtype=float),
        play_mode="end_with_zero",
    )
    if result_i != 0 or result_q != 0:
        raise RuntimeError(
            f"Wave upload failed for {dac_name}: I={result_i}, Q={result_q}"
        )


def extract_channel(values, channel: int, expected_length: int) -> np.ndarray:
    """Convert a driver IQ result into one 1-D array for the selected channel."""

    array = np.asarray(values)
    if array.ndim == 1:
        selected = array
    else:
        selected = np.asarray(array[channel])

    selected = np.ravel(selected).astype(float)
    if len(selected) != expected_length:
        raise RuntimeError(
            f"ADC returned {len(selected)} values; expected {expected_length}"
        )
    if not np.all(np.isfinite(selected)):
        raise RuntimeError("ADC returned NaN or infinite values")
    return selected


def write_results_csv(path: Path, results: list[dict]) -> None:
    fields = [
        "drive_amplitude_norm",
        "I_mean",
        "Q_mean",
        "I_std",
        "Q_std",
        "IQ_abs",
        "IQ_phase_rad",
        "IQ_projection",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def add_iq_projection(results: list[dict]) -> None:
    points = np.asarray(
        [[row["I_mean"], row["Q_mean"]] for row in results],
        dtype=float,
    )
    centered = points - points.mean(axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    projection = centered @ vh[0]

    # Fix the arbitrary PCA sign so repeat plots are easier to compare.
    if len(projection) >= 2 and projection[-1] < projection[0]:
        projection *= -1

    for row, value in zip(results, projection):
        row["IQ_projection"] = float(value)


def save_rabi_plot(path: Path, results: list[dict]) -> None:
    amplitude = np.asarray(
        [row["drive_amplitude_norm"] for row in results], dtype=float
    )
    projection = np.asarray(
        [row["IQ_projection"] for row in results], dtype=float
    )
    i_mean = np.asarray([row["I_mean"] for row in results], dtype=float)
    q_mean = np.asarray([row["Q_mean"] for row in results], dtype=float)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].plot(amplitude, projection, "o-", markersize=4)
    axes[0].set_xlabel("Normalized Qubit drive amplitude")
    axes[0].set_ylabel("Mean IQ projection")
    axes[0].set_title("Amplitude Rabi")
    axes[0].grid(alpha=0.3)

    axes[1].plot(i_mean, q_mean, "o-", markersize=4)
    axes[1].set_xlabel("Mean I")
    axes[1].set_ylabel("Mean Q")
    axes[1].set_title("Mean IQ trajectory")
    axes[1].axis("equal")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    validate_config()
    MmcsDriver, VNA, LO, LogFolder, logfolder_backend = load_dependencies()

    print("\n2026-07-12 MMCS amplitude-Rabi")
    print(f"LogFolder backend : {logfolder_backend}")
    print(f"Data folder       : {DATA_FOLDER}")
    print(
        "Qubit             : "
        f"target={QUBIT_FREQ_HZ/1e9:.6f} GHz, "
        f"LO={QUBIT_LO_HZ/1e9:.6f} GHz, IF={QUBIT_IF_HZ/1e6:+.3f} MHz"
    )
    print(
        "Readout           : "
        f"target={RESONATOR_FREQ_HZ/1e9:.6f} GHz, "
        f"LO={READOUT_LO_HZ/1e9:.6f} GHz, IF={READOUT_IF_HZ/1e6:+.3f} MHz"
    )
    print(
        "Amplitude scan    : "
        f"{DRIVE_AMPLITUDES[0]:.3f} to {DRIVE_AMPLITUDES[-1]:.3f}, "
        f"{len(DRIVE_AMPLITUDES)} points"
    )
    print(f"Safety profile    : {SAFETY_PROFILE}")
    print(f"Drive pulse       : {DRIVE_PULSE_NS:.1f} ns")
    print(f"Readout amplitude : {READOUT_AMPLITUDE:.3f} normalized")
    print(f"Repetitions/point : {REPS}")
    print(
        "RF chain record   : "
        f"input attenuation {INPUT_LINE_ATTENUATION_MIN_DB:.0f}-"
        f"{INPUT_LINE_ATTENUATION_MAX_DB:.0f} dB, "
        f"return gain {RETURN_CHAIN_GAIN_DB:.0f} dB"
    )
    print("\nThe program will automatically configure:")
    print(
        f"  VNA LO      = {READOUT_LO_HZ/1e9:.6f} GHz, "
        f"{READOUT_LO_POWER_DBM:+.1f} dBm, CW output ON"
    )
    print(
        f"  Anritsu LO  = {QUBIT_LO_HZ/1e9:.6f} GHz, "
        f"{QUBIT_LO_POWER_DBM:+.1f} dBm, output ON"
    )
    print(
        "The LO powers above are mixer-LO setpoints. They are not powers at "
        "the chip."
    )

    if REQUIRE_RUN_CONFIRMATION:
        answer = input("Type RUN after checking the LO cables and RF chain: ")
        if answer.strip() != "RUN":
            print(
                "Cancelled. Instruments and MMCS were not connected, and no "
                "LogFolder was created."
            )
            return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    dset = LogFolder.new(DATA_FOLDER)
    dset.meta.title = f"amplitude Rabi {timestamp}"
    dset.add_const_to_head(
        created_at=datetime.now().isoformat(timespec="seconds"),
        mmcs_ip=MMCS_IP,
        box_name=BOX_NAME,
        vna_resource=VNA_RESOURCE,
        anritsu_resource=ANRITSU_RESOURCE,
        qubit_xy_dac=QUBIT_XY_DAC_NAME,
        readout_dac=READOUT_DAC_NAME,
        readout_adc=READOUT_ADC_NAME,
        adc_freq_channel=ADC_FREQ_CHANNEL,
        qubit_freq_GHz=QUBIT_FREQ_HZ / 1e9,
        qubit_lo_GHz=QUBIT_LO_HZ / 1e9,
        qubit_if_MHz=QUBIT_IF_HZ / 1e6,
        readout_freq_GHz=RESONATOR_FREQ_HZ / 1e9,
        readout_lo_GHz=READOUT_LO_HZ / 1e9,
        readout_if_MHz=READOUT_IF_HZ / 1e6,
        qubit_lo_power_setpoint_dBm=QUBIT_LO_POWER_DBM,
        readout_lo_power_setpoint_dBm=READOUT_LO_POWER_DBM,
        drive_pulse_ns=DRIVE_PULSE_NS,
        drive_amplitude_min=float(DRIVE_AMPLITUDES[0]),
        drive_amplitude_max=float(DRIVE_AMPLITUDES[-1]),
        drive_amplitude_points=len(DRIVE_AMPLITUDES),
        readout_amplitude_norm=READOUT_AMPLITUDE,
        readout_length_ns=READOUT_LENGTH_NS,
        adc_sample_length=ADC_SAMPLE_LENGTH,
        reps=REPS,
        cycle_period_ns=CYCLE_PERIOD_NS,
        input_line_attenuation_min_dB=INPUT_LINE_ATTENUATION_MIN_DB,
        input_line_attenuation_max_dB=INPUT_LINE_ATTENUATION_MAX_DB,
        return_chain_gain_dB=RETURN_CHAIN_GAIN_DB,
        absolute_chip_power_calibrated=False,
        safety_profile=SAFETY_PROFILE,
        swap_iq=SWAP_IQ,
        q_sign=Q_SIGN,
    )

    # Supplementary files are placed under the same dated project folder.
    csv_path = DATA_FOLDER / f"rabi_{timestamp}.csv"
    plot_path = DATA_FOLDER / f"rabi_{timestamp}.png"
    error_path = DATA_FOLDER / f"rabi_{timestamp}_error.txt"
    summary_path = DATA_FOLDER / f"rabi_{timestamp}_summary.json"

    results: list[dict] = []
    mmcs = None
    vna = None
    qubit_lo = None

    try:
        print("\nConnecting and configuring the two LO instruments ...")
        vna = VNA(VNA_RESOURCE)
        qubit_lo = LO(ANRITSU_RESOURCE)

        print(f"VNA IDN     : {identify_instrument(vna)}")
        print(f"Anritsu IDN : {identify_instrument(qubit_lo)}")

        try:
            configure_vna_as_readout_lo(vna)
            configure_anritsu_as_qubit_lo(qubit_lo)
        except BaseException:
            # If the second instrument fails after the first was enabled, turn
            # both off before propagating the configuration error.
            for instrument in (qubit_lo, vna):
                if instrument is not None:
                    try:
                        set_output_enabled(instrument, False)
                    except Exception:
                        pass
            raise

        vna_freq_readback = optional_readback(vna, "get_center_Hz")
        vna_power_readback = optional_readback(vna, "get_power_dBm")
        anritsu_freq_readback = optional_readback(qubit_lo, "get_freq_Hz")
        anritsu_power_readback = optional_readback(qubit_lo, "get_power_dBm")
        vna_output_readback = get_output_enabled(vna)
        anritsu_output_readback = get_output_enabled(qubit_lo)

        if vna_output_readback is False:
            raise RuntimeError("VNA reports RF output OFF after configuration")
        if anritsu_output_readback is False:
            raise RuntimeError(
                "Anritsu reports RF output OFF after configuration"
            )

        print(
            "VNA configured     : "
            f"{READOUT_LO_HZ/1e9:.6f} GHz, "
            f"{READOUT_LO_POWER_DBM:+.1f} dBm, output ON"
        )
        print(
            "Anritsu configured : "
            f"{QUBIT_LO_HZ/1e9:.6f} GHz, "
            f"{QUBIT_LO_POWER_DBM:+.1f} dBm, output ON"
        )
        print(
            "RF output readback : "
            f"VNA={vna_output_readback!r}, "
            f"Anritsu={anritsu_output_readback!r}"
        )

        dset.add_const_to_head(
            vna_idn=identify_instrument(vna),
            anritsu_idn=identify_instrument(qubit_lo),
            vna_frequency_readback_Hz=vna_freq_readback,
            vna_power_readback_dBm=vna_power_readback,
            anritsu_frequency_readback_Hz=anritsu_freq_readback,
            anritsu_power_readback_dBm=anritsu_power_readback,
            vna_output_readback=vna_output_readback,
            anritsu_output_readback=anritsu_output_readback,
            instrument_control="automatic",
        )

        print(f"\nConnecting to MMCS {MMCS_IP} ...")
        mmcs = MmcsDriver(box_ip_dict={BOX_NAME: MMCS_IP})
        stop_mmcs(mmcs)

        required_dac = {QUBIT_XY_DAC_NAME, READOUT_DAC_NAME}
        missing_dac = sorted(required_dac.difference(mmcs.da))
        if missing_dac:
            raise RuntimeError(f"Missing DAC channels: {missing_dac}")
        if READOUT_ADC_NAME not in mmcs.ad:
            raise RuntimeError(f"Missing ADC channel: {READOUT_ADC_NAME}")

        # Upload the readout waveform once.
        readout_i, readout_q = make_iq_wave(
            READOUT_IF_HZ,
            READOUT_AMPLITUDE,
            READOUT_LENGTH_NS,
            envelope="rect",
        )
        set_single_iq_wave(
            mmcs,
            READOUT_DAC_NAME,
            readout_i,
            readout_q,
        )

        # Configure ADC demodulation once.
        mmcs.ad_set_sample_parameter(
            name=READOUT_ADC_NAME,
            sample_len=int(ADC_SAMPLE_LENGTH),
            cycle_times=int(REPS),
        )
        demo_cos, demo_sin = mmcs.tools.gen_normalized_demodulation_factor(
            IF_freq=READOUT_IF_HZ,
            demo_length=int(ADC_SAMPLE_LENGTH),
        )
        mmcs.ad_set_demodulation_factor(
            name=READOUT_ADC_NAME,
            freq_ch=ADC_FREQ_CHANNEL,
            demo_i=np.asarray(demo_sin),
            demo_q=np.asarray(demo_cos),
        )

        readout_start_ns = round_up(
            DRIVE_PULSE_NS + DRIVE_READOUT_GAP_NS,
            4,
        )
        xy_trigger_ns = round_up(
            BASE_TRIGGER_NS + XY_TRIGGER_DELAY_NS,
            4,
        )
        readout_trigger_ns = round_up(
            BASE_TRIGGER_NS
            + readout_start_ns
            + READOUT_TRIGGER_DELAY_NS,
            4,
        )
        adc_trigger_ns = round_up(
            BASE_TRIGGER_NS
            + readout_start_ns
            + ADC_TRIGGER_DELAY_NS,
            4,
        )

        print(
            "Trigger times      : "
            f"XY={xy_trigger_ns} ns, readout={readout_trigger_ns} ns, "
            f"ADC={adc_trigger_ns} ns"
        )

        def measure_point(_drive_amplitude_norm):
            amplitude = float(_drive_amplitude_norm)

            drive_i, drive_q = make_iq_wave(
                QUBIT_IF_HZ,
                amplitude,
                DRIVE_PULSE_NS,
                envelope="hann",
            )
            set_single_iq_wave(
                mmcs,
                QUBIT_XY_DAC_NAME,
                drive_i,
                drive_q,
            )

            mmcs.da_set_level2_trigger_ram(
                name=QUBIT_XY_DAC_NAME,
                time_stamp_list_ns=[xy_trigger_ns],
                cmd_list=[mmcs.trigger_start],
            )
            mmcs.da_set_level2_trigger_ram(
                name=READOUT_DAC_NAME,
                time_stamp_list_ns=[readout_trigger_ns],
                cmd_list=[mmcs.trigger_start],
            )
            mmcs.ad_clear_stored_data(name=READOUT_ADC_NAME)
            mmcs.ad_set_level2_trigger_ram(
                name=READOUT_ADC_NAME,
                time_stamp_list_ns=[adc_trigger_ns],
                cmd_list=[mmcs.trigger_start],
            )

            mmcs.sys_set_level1_trigger(
                cycle_times=int(REPS),
                cycle_period_ns=int(CYCLE_PERIOD_NS),
            )
            mmcs.sys_run_level1_trigger(master_box_name=BOX_NAME)
            mmcs.sys_wait_until_finish(master_box_name=BOX_NAME)

            _, _, i_ave, q_ave, _ = mmcs.ad_get_IQ(
                name=READOUT_ADC_NAME
            )
            i_values = extract_channel(i_ave, ADC_FREQ_CHANNEL, REPS)
            q_values = extract_channel(q_ave, ADC_FREQ_CHANNEL, REPS)

            mean_i = float(i_values.mean())
            mean_q = float(q_values.mean())
            mean_iq = mean_i + 1j * mean_q
            row = {
                "drive_amplitude_norm": amplitude,
                "I_mean": mean_i,
                "Q_mean": mean_q,
                "I_std": float(i_values.std()),
                "Q_std": float(q_values.std()),
                "IQ_abs": float(abs(mean_iq)),
                "IQ_phase_rad": float(np.angle(mean_iq)),
                "IQ_projection": "",
            }
            results.append(row)

            # Independent checkpoint in addition to LogFolder's own save.
            write_results_csv(csv_path, results)
            print(
                f"[{len(results):02d}/{len(DRIVE_AMPLITUDES)}] "
                f"amp={amplitude:.3f}, I={mean_i:.6g}, Q={mean_q:.6g}"
            )

            return {
                "I_mean": mean_i,
                "Q_mean": mean_q,
                "I_std": row["I_std"],
                "Q_std": row["Q_std"],
                "IQ_abs": row["IQ_abs"],
                "IQ_phase_rad": row["IQ_phase_rad"],
            }

        # LogFolder saves each acquired point under DATA_FOLDER.
        dset.capture(measure_point, [DRIVE_AMPLITUDES])

        if len(results) != len(DRIVE_AMPLITUDES):
            raise RuntimeError(
                f"Only {len(results)} of {len(DRIVE_AMPLITUDES)} points finished"
            )

        add_iq_projection(results)
        write_results_csv(csv_path, results)
        save_rabi_plot(plot_path, results)

        summary = {
            "status": "complete",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "logfolder_title": dset.meta.title,
            "data_folder": str(DATA_FOLDER),
            "csv": str(csv_path),
            "plot": str(plot_path),
            "points": len(results),
        }
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\nAmplitude-Rabi acquisition complete.")
        print(f"LogFolder project : {DATA_FOLDER}")
        print(f"CSV               : {csv_path}")
        print(f"Plot              : {plot_path}")

    except BaseException:
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        if results:
            try:
                add_iq_projection(results)
                write_results_csv(csv_path, results)
                save_rabi_plot(plot_path, results)
            except Exception:
                pass
        raise

    finally:
        if mmcs is not None:
            try:
                stop_mmcs(mmcs)
                print("MMCS outputs stopped and trigger RAM cleared.")
            except Exception as stop_error:
                print(f"WARNING: automatic MMCS stop failed: {stop_error}")

        for label, instrument in (
            ("Anritsu", qubit_lo),
            ("VNA", vna),
        ):
            if instrument is not None:
                try:
                    set_output_enabled(instrument, False)
                    print(f"{label} RF output OFF.")
                except Exception as output_error:
                    print(
                        f"WARNING: failed to turn {label} output off: "
                        f"{output_error}"
                    )


if __name__ == "__main__":
    main()
