"""Generate an MMCS DAC waveform and measure it with a spectrum analyzer.

Physical setup: connect the selected MMCS DAC output to the spectrum-analyzer
RF input through suitable attenuation.  The script is a dry run unless
``--run-hardware`` is supplied explicitly.
"""

from __future__ import annotations

import argparse
import math
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from control import InstrumentFactory, SpectrumAnalyzerController, load_control_config
from control.config import MmcsDeviceConfig
from control.core.exceptions import AcquisitionError, ValidationError
from control.domain.mmcs import (
    DacChannel,
    DacPlayMode,
    DacProgram,
    DacWaveform,
    MmcsExecutor,
    MmcsProgram,
    PlaylistEntry,
    TriggerCommand,
    TriggerEvent,
    validate_program,
)
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace

DAC_SAMPLE_RATE_HZ = 2_000_000_000.0
DEFAULT_PERIOD_NS = 1_000_000
DEFAULT_START_TRIGGER_NS = 40


@dataclass(frozen=True, slots=True)
class SpectrumPeak:
    frequency_hz: float
    power_dbm: float
    median_floor_dbm: float
    prominence_db: float


class MmcsExecutorLike(Protocol):
    driver: object

    def prepare(self, program: MmcsProgram): ...

    def run(self, prepared, *, timeout_s: float): ...


class SpectrumControllerLike(Protocol):
    def acquire(self, config: SpectrumSweepConfig, *, timeout_s: float) -> SpectrumTrace: ...


def _aligned_periodic_sample_count(
    frequency_hz: float, *, minimum_samples: int = 800
) -> tuple[int, float]:
    if not np.isfinite(frequency_hz) or not 0 < frequency_hz < DAC_SAMPLE_RATE_HZ / 2:
        raise ValidationError("frequency_hz must be finite and below the 1 GHz Nyquist limit")
    if minimum_samples < 8:
        raise ValidationError("minimum_samples must be at least 8")
    samples_per_cycle = max(2, round(DAC_SAMPLE_RATE_HZ / frequency_hz))
    block = math.lcm(samples_per_cycle, 8)
    sample_count = math.ceil(minimum_samples / block) * block
    actual_frequency_hz = DAC_SAMPLE_RATE_HZ / samples_per_cycle
    return sample_count, actual_frequency_hz


def generate_periodic_waveform(
    kind: str,
    *,
    frequency_hz: float,
    amplitude: float,
    minimum_samples: int = 800,
) -> tuple[np.ndarray, float]:
    """Return an 8-sample-aligned periodic sine or square waveform."""
    if not np.isfinite(amplitude) or not 0 < amplitude <= 1:
        raise ValidationError("amplitude must be finite and in (0, 1]")
    sample_count, actual_frequency_hz = _aligned_periodic_sample_count(
        frequency_hz, minimum_samples=minimum_samples
    )
    time_s = np.arange(sample_count) / DAC_SAMPLE_RATE_HZ
    phase = 2 * np.pi * actual_frequency_hz * time_s
    if kind == "sine":
        samples = amplitude * np.sin(phase)
    elif kind == "square":
        samples = amplitude * np.where(np.sin(phase) >= 0, 1.0, -1.0)
    else:
        raise ValidationError("waveform kind must be 'sine' or 'square'")
    return samples, actual_frequency_hz


def load_arbitrary_waveform(path: str | Path, *, amplitude: float) -> np.ndarray:
    """Load a user waveform from a one-dimensional NumPy ``.npy`` file."""
    if not np.isfinite(amplitude) or not 0 < amplitude <= 1:
        raise ValidationError("amplitude must be finite and in (0, 1]")
    try:
        samples = np.asarray(np.load(Path(path), allow_pickle=False), dtype=float)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"Cannot load waveform file {path!s}: {exc}") from exc
    if samples.ndim != 1 or samples.size == 0 or samples.size % 8:
        raise ValidationError("Waveform file must contain a non-empty 1-D array aligned to 8 samples")
    if not np.all(np.isfinite(samples)):
        raise ValidationError("Waveform file contains non-finite samples")
    peak = float(np.max(np.abs(samples)))
    if peak == 0:
        raise ValidationError("Waveform file cannot contain only zeros")
    return samples / peak * amplitude


def build_mmcs_output_program(
    waveform: np.ndarray,
    *,
    board_id: str,
    channel: DacChannel,
    master_box: str,
    run_duration_s: float,
    period_ns: int = DEFAULT_PERIOD_NS,
) -> MmcsProgram:
    """Build a finite program that cycles the waveform for the measurement window."""
    if not np.isfinite(run_duration_s) or run_duration_s <= 0:
        raise ValidationError("run_duration_s must be positive")
    if not isinstance(period_ns, int) or period_ns < 12 or period_ns % 4:
        raise ValidationError("period_ns must be an integer multiple of 4 and at least 12 ns")
    stop_ns = period_ns - 4
    if stop_ns <= DEFAULT_START_TRIGGER_NS:
        raise ValidationError("period_ns leaves no room between START and STOP triggers")
    repetitions = max(1, math.ceil(run_duration_s / (period_ns * 1e-9)))
    program = MmcsProgram(
        master_box=master_box,
        period_ns=period_ns,
        repetitions=repetitions,
        dac_programs=(
            DacProgram(
                board_id=board_id,
                channel=channel,
                waveforms=(DacWaveform(waveform),),
                playlist=(PlaylistEntry(waveform_index=0),),
                play_mode=DacPlayMode.CYCLE,
                triggers=(
                    TriggerEvent(DEFAULT_START_TRIGGER_NS, TriggerCommand.START),
                    TriggerEvent(stop_ns, TriggerCommand.STOP),
                ),
            ),
        ),
    )
    validate_program(program)
    return program


def analyze_spectrum(trace: SpectrumTrace) -> SpectrumPeak:
    if trace.power_dbm.size == 0:
        raise AcquisitionError("Spectrum trace is empty")
    peak_index = int(np.argmax(trace.power_dbm))
    floor = float(np.median(trace.power_dbm))
    power = float(trace.power_dbm[peak_index])
    return SpectrumPeak(
        frequency_hz=float(trace.frequency_hz[peak_index]),
        power_dbm=power,
        median_floor_dbm=floor,
        prominence_db=power - floor,
    )


def acquire_while_mmcs_runs(
    executor: MmcsExecutorLike,
    analyzer: SpectrumControllerLike,
    *,
    program: MmcsProgram,
    spectrum_config: SpectrumSweepConfig,
    mmcs_timeout_s: float,
    spectrum_timeout_s: float,
    startup_delay_s: float = 0.1,
) -> SpectrumTrace:
    """Repeat a finite MMCS program while the analyzer acquires.

    The vendor wait and stop operations share one UDP socket and cannot safely
    run concurrently.  Repeating a short finite program bounds shutdown latency
    without issuing commands while a vendor wait is active.
    """
    if startup_delay_s < 0:
        raise ValidationError("startup_delay_s cannot be negative")
    prepared = executor.prepare(program)
    stop_requested = threading.Event()

    def output_loop():
        completed_runs = 0
        while not stop_requested.is_set():
            executor.run(prepared, timeout_s=mmcs_timeout_s)
            completed_runs += 1
        return completed_runs

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mmcs-output")
    future: Future = pool.submit(output_loop)
    primary_error: BaseException | None = None
    try:
        time.sleep(startup_delay_s)
        if future.done():
            future.result()
        return analyzer.acquire(spectrum_config, timeout_s=spectrum_timeout_s)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        stop_requested.set()
        try:
            future.result(timeout=mmcs_timeout_s + 1.0)
        except BaseException as output_exc:
            if primary_error is not None:
                primary_error.add_note(f"Finishing MMCS output also failed: {output_exc}")
            else:
                raise AcquisitionError("MMCS output failed during spectrum acquisition") from output_exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


def save_trace_csv(trace: SpectrumTrace, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(
        output,
        np.column_stack((trace.frequency_hz, trace.power_dbm)),
        delimiter=",",
        header="frequency_hz,power_dbm",
        comments="",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/instruments.local.toml")
    parser.add_argument("--mmcs-name", default="mmcs")
    parser.add_argument("--spectrum-name", default="spectrum")
    parser.add_argument("--dac-board", required=True, help="e.g. da_box1pcie1ch12")
    parser.add_argument("--dac-channel", choices=("i", "q"), default="i")
    parser.add_argument("--waveform", choices=("sine", "square"), default="sine")
    parser.add_argument("--waveform-file", type=Path)
    parser.add_argument("--frequency-hz", type=float, default=20e6)
    parser.add_argument("--amplitude", type=float, default=0.02)
    parser.add_argument("--minimum-samples", type=int, default=800)
    parser.add_argument(
        "--chunk-duration-s",
        type=float,
        default=0.25,
        help="finite MMCS chunk duration; bounds shutdown latency",
    )
    parser.add_argument("--period-ns", type=int, default=DEFAULT_PERIOD_NS)
    parser.add_argument("--center-hz", type=float)
    parser.add_argument("--span-hz", type=float, default=10e6)
    parser.add_argument("--points", type=int, default=501)
    parser.add_argument("--rbw-hz", type=float, default=100e3)
    parser.add_argument("--attenuation-db", type=float, default=20.0)
    parser.add_argument("--spectrum-timeout-s", type=float, default=30.0)
    parser.add_argument("--startup-delay-s", type=float, default=0.1)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument(
        "--run-hardware",
        action="store_true",
        help="required to connect to and operate laboratory hardware",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.waveform_file is None:
        waveform, actual_frequency_hz = generate_periodic_waveform(
            args.waveform,
            frequency_hz=args.frequency_hz,
            amplitude=args.amplitude,
            minimum_samples=args.minimum_samples,
        )
    else:
        waveform = load_arbitrary_waveform(args.waveform_file, amplitude=args.amplitude)
        actual_frequency_hz = args.frequency_hz

    config = load_control_config(args.config)
    mmcs_config = config.require(args.mmcs_name, MmcsDeviceConfig)
    program = build_mmcs_output_program(
        waveform,
        board_id=args.dac_board,
        channel=DacChannel(args.dac_channel),
        master_box=mmcs_config.master_box,
        run_duration_s=args.chunk_duration_s,
        period_ns=args.period_ns,
    )
    center_hz = args.center_hz if args.center_hz is not None else actual_frequency_hz
    spectrum_config = SpectrumSweepConfig.from_center_span(
        center_hz=center_hz,
        span_hz=args.span_hz,
        points=args.points,
        resolution_bandwidth_hz=args.rbw_hz,
        input_attenuation_db=args.attenuation_db,
    )

    print(
        f"Prepared {waveform.size} samples, peak={np.max(np.abs(waveform)):.4f}, "
        f"tone={actual_frequency_hz / 1e6:.6f} MHz, "
        f"output window≈{program.period_ns * program.repetitions / 1e9:.3f} s"
    )
    if not args.run_hardware:
        print("Dry run only. Add --run-hardware after checking cabling and attenuation.")
        return 0

    factory = InstrumentFactory(config)
    with factory.create_mmcs(args.mmcs_name) as mmcs_driver:
        with factory.create_spectrum_analyzer(args.spectrum_name) as spectrum_driver:
            executor = MmcsExecutor(
                mmcs_driver,
                cleanup_timeout_s=mmcs_config.cleanup_timeout_s,
            )
            trace = acquire_while_mmcs_runs(
                executor,
                SpectrumAnalyzerController(spectrum_driver),
                program=program,
                spectrum_config=spectrum_config,
                mmcs_timeout_s=args.chunk_duration_s + 5.0,
                spectrum_timeout_s=args.spectrum_timeout_s,
                startup_delay_s=args.startup_delay_s,
            )

    peak = analyze_spectrum(trace)
    print(
        f"Peak: {peak.frequency_hz / 1e6:.6f} MHz, {peak.power_dbm:.2f} dBm; "
        f"median floor: {peak.median_floor_dbm:.2f} dBm; "
        f"prominence: {peak.prominence_db:.2f} dB"
    )
    if args.output_csv is not None:
        save_trace_csv(trace, args.output_csv)
        print(f"Saved spectrum to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
