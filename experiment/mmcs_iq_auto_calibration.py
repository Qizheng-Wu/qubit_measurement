"""Dry-run-first entry point for four-parameter IQ mixer calibration."""

from control import InstrumentFactory
from control.config import MmcsDeviceConfig
from control.db import (
    IqCalibrationRepository,
    create_calibration_engine,
    create_session_factory,
    default_calibration_database_path,
)
from control.domain.calibration import IqAutoCalibrationSpec
from control.domain.mmcs import IqCalibration, Sideband
from control.services import IqAutoCalibrationService
from experiment.config import load_config

RUN_HARDWARE = False


def build_spec() -> IqAutoCalibrationSpec:
    config = load_config()
    mmcs_config = config.require("mmcs", MmcsDeviceConfig)
    signal_path_name = "qubit_xy_q1"
    signal_path = mmcs_config.require_signal_path(signal_path_name)
    board = mmcs_config.require_dac_board(signal_path.dac_board_id)
    awg = config.defaults.mmcs_awg
    return IqAutoCalibrationSpec(
        signal_path=signal_path_name,
        board_id=signal_path.dac_board_id,
        master_box="box1",
        sample_rate_hz=board.sample_rate_hz,
        lo_frequency_hz=5.0e9,
        if_frequency_hz=20.0e6,
        sideband=Sideband.UPPER,
        amplitude=0.02,
        minimum_samples=awg.minimum_waveform_samples,
        period_ns=awg.period_ns,
        start_trigger_ns=awg.start_trigger_ns,
        spectrum_span_hz=2.0e6,
        spectrum_points=201,
        resolution_bandwidth_hz=10.0e3,
        input_attenuation_db=20.0,
        measurement_timeout_s=5.0,
        initial_calibration=IqCalibration(
            q_over_i_gain=signal_path.q_over_i_gain,
            i_offset=signal_path.i_offset,
            q_offset=signal_path.q_offset,
            q_phase_correction_rad=signal_path.q_phase_correction_rad,
        ),
    )


def print_plan(spec: IqAutoCalibrationSpec) -> None:
    maximum_candidates = 6 + 2 * spec.max_evaluations_per_stage
    print(f"signal_path={spec.signal_path}, board={spec.board_id}")
    print(f"initial_calibration={spec.initial_calibration.model_dump()}")
    print(
        f"LO={spec.lo_frequency_hz / 1e9:.9g} GHz, "
        f"target={spec.target_frequency_hz / 1e9:.9g} GHz, "
        f"image={spec.image_frequency_hz / 1e9:.9g} GHz"
    )
    print(f"offset_bounds={spec.offset_bounds}")
    print(f"imbalance_bounds={spec.imbalance_bounds}")
    print(
        f"maximum_candidates={maximum_candidates}, "
        f"maximum_marker_sweeps={maximum_candidates * spec.measurement_repetitions}"
    )
    print(f"sqlite={default_calibration_database_path()}")


def main() -> int:
    config = load_config()
    spec = build_spec()
    print_plan(spec)
    if not RUN_HARDWARE:
        print("Dry run only. Set RUN_HARDWARE=True after verifying LO and analyzer limits.")
        return 0

    factory = InstrumentFactory(config)
    mmcs = factory.create_mmcs_service("mmcs")
    spectrum = factory.create_spectrum_analyzer_service("spectrum")
    engine = create_calibration_engine()
    repository = IqCalibrationRepository(create_session_factory(engine))
    calibrator = IqAutoCalibrationService(mmcs, spectrum, repository)
    try:
        with mmcs.connected(), spectrum.connected():
            result = calibrator.calibrate(spec)
    finally:
        engine.dispose()

    print(f"run_id={result.run_id}, converged={result.optimizer_converged}")
    print(result.termination_reason)
    print(result.toml_snippet(spec.signal_path, spec.board_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
