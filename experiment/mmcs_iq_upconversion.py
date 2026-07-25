"""Output a calibrated continuous IQ pair for external single-sideband upconversion."""

from control import InstrumentFactory
from control.config import MmcsDeviceConfig
from control.domain.mmcs import IqCalibration, IqToneSpec, Sideband
from control.services import build_iq_upconversion_program, generate_iq_tone
from experiment.config import load_config

RUN_HARDWARE = False


def main() -> int:
    config = load_config()
    mmcs_name = "mmcs"
    board_id = "da_box1pcie1ch12"
    master_box = "box1"
    run_duration_s = 30.0
    board = config.require(mmcs_name, MmcsDeviceConfig).require_dac_board(board_id)
    defaults = config.defaults.mmcs_awg

    tone = generate_iq_tone(
        IqToneSpec(
            sample_rate_hz=board.sample_rate_hz,
            if_frequency_hz=20e6,
            amplitude=0.02,
            phase_rad=0.0,
            minimum_samples=defaults.minimum_waveform_samples,
            sideband=Sideband.UPPER,
            calibration=IqCalibration(),
        )
    )
    program = build_iq_upconversion_program(
        tone,
        board_id=board_id,
        master_box=master_box,
        run_duration_s=run_duration_s,
        period_ns=defaults.period_ns,
        start_trigger_ns=defaults.start_trigger_ns,
    )
    print(
        f"board={board_id}, sideband={tone.spec.sideband.value}, "
        f"requested_IF={tone.spec.if_frequency_hz / 1e6:.6f} MHz, "
        f"actual_IF={tone.actual_if_frequency_hz / 1e6:.6f} MHz, "
        f"samples={tone.i_waveform.samples.size}"
    )
    if not RUN_HARDWARE:
        print("Dry run only. Set RUN_HARDWARE=True after checking the IQ mixer and attenuation.")
        return 0

    service = InstrumentFactory(config).create_mmcs_service(mmcs_name)
    with service.connected():
        with service.running(program) as run:
            run.result(timeout_s=run_duration_s + defaults.safety_margin_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
