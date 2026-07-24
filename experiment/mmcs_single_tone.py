from control import InstrumentFactory
from control.config import MmcsDeviceConfig
from control.domain.mmcs import SingleToneSpec
from control.services import generate_single_tone, build_cyclic_dac_program
from experiment.config import load_config
from control.domain.mmcs import DacChannel

def main():
    config = load_config()
    factory = InstrumentFactory(config)

    mmcs_name = "mmcs"
    board_id = "da_box1pcie1ch12"
    master_box = "box1"
    channel = DacChannel.I

    mmcs_service = factory.create_mmcs_service(mmcs_name)
    mmcs_config = config.require(mmcs_name, MmcsDeviceConfig)
    awg_defaults = config.defaults.mmcs_awg

    board = mmcs_config.require_dac_board(board_id)

    tone = generate_single_tone(
        SingleToneSpec(
            sample_rate_hz=board.sample_rate_hz,
            frequency_hz=20e6,
            amplitude=0.02,
            phase_rad=0,
            minimum_samples=awg_defaults.minimum_waveform_samples,
        )
    )

    program = build_cyclic_dac_program(
        tone.waveform,
        board_id=board_id,
        channel=channel,
        master_box=master_box,
        run_duration_s=30,
        period_ns=awg_defaults.period_ns,
        start_trigger_ns=awg_defaults.start_trigger_ns,
    )

    with mmcs_service.connected():
        with mmcs_service.running(program):
            return 0
