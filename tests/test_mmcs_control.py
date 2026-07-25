from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError as PydanticValidationError

from control.core.exceptions import InstrumentCommandError, InstrumentStateError
from control.domain.mmcs import (
    AdcProgram,
    DacBoardProgram,
    DacChannel,
    DacChannelProgram,
    DacPlayMode,
    DacWaveform,
    DemodulationWeights,
    IqCalibration,
    IqToneSpec,
    MmcsProgram,
    PlaylistEntry,
    SingleToneSpec,
    Sideband,
    TriggerCommand,
    TriggerEvent,
)
from control.driver.mmcs import MmcsHardwareDriver
from control.services import (
    MmcsService,
    build_cyclic_dac_program,
    build_iq_upconversion_program,
    generate_iq_tone,
    generate_single_tone,
)
from control.transport.mmcs_vendor import MmcsVendorTransport


class FakeMmcsBackend:
    def __init__(self, *, fail_method=None, fail_call_number=None):
        self.calls = []
        self.fail_method = fail_method
        self.fail_call_number = fail_call_number
        self.method_call_counts = {}
        self.closed = False

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            self.method_call_counts[name] = self.method_call_counts.get(name, 0) + 1
            if name == self.fail_method and (
                self.fail_call_number is None
                or self.method_call_counts[name] == self.fail_call_number
            ):
                raise RuntimeError("injected failure")
            if name == "ad_get_IQ":
                return tuple(np.zeros((12, 2)) + index for index in range(5))
            return 0

        return method

    def sys_close(self):
        self.calls.append(("sys_close", (), {}))
        self.closed = True


def make_program(**changes):
    waveform = DacWaveform(samples=np.zeros(8))
    playlist = (PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),)
    weights = DemodulationWeights(channel=0, i=np.zeros(8), q=np.zeros(8))
    values = dict(
        master_box="box1",
        period_ns=100,
        repetitions=2,
        dac_boards=(
            DacBoardProgram(
                board_id="da_box1pcie1ch12",
                triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
                channels=tuple(
                    DacChannelProgram(
                        channel=channel,
                        waveforms=(waveform,),
                        playlist=playlist,
                        play_mode=DacPlayMode.END_WITH_ZERO,
                    )
                    for channel in DacChannel
                ),
            ),
        ),
        adc_programs=(
            AdcProgram(
                board_id="ad_box1pcie1ch12",
                sample_length=8,
                demodulations=(weights,),
                triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
            ),
        ),
    )
    values.update(changes)
    return MmcsProgram(**values)


def make_service(backend):
    transport = MmcsVendorTransport(
        {"box1": "192.0.2.1"}, backend_factory=lambda boxes: backend
    )
    driver = MmcsHardwareDriver(transport, shutdown_timeout_s=5)
    return transport, MmcsService(driver, cleanup_timeout_s=5)


def test_each_run_prepares_and_result_is_cached():
    backend = FakeMmcsBackend()
    _, service = make_service(backend)
    program = make_program()

    with service.connected():
        with service.running(program) as first_run:
            first = first_run.result(timeout_s=2)
            assert first_run.result(timeout_s=2) is first
        with service.running(program) as second_run:
            second = second_run.result(timeout_s=2)

    assert set(first.iq_by_adc) == {"ad_box1pcie1ch12"}
    assert first.iq_by_adc["ad_box1pcie1ch12"].i_sum.shape == (12, 2)
    assert first.program_fingerprint == second.program_fingerprint
    names = [call[0] for call in backend.calls]
    assert names.count("da_set_multi_waveform") == 4
    assert names.count("da_set_level2_trigger_ram") == 2
    assert names.count("sys_run_level1_trigger") == 2
    with pytest.raises(ValueError):
        first.iq_by_adc["ad_box1pcie1ch12"].i_sum[0, 0] = 1


def test_unconsumed_run_stops_and_completed_run_waits():
    backend = FakeMmcsBackend()
    _, service = make_service(backend)
    program = make_program(adc_programs=())

    with service.connected():
        with service.running(program):
            pass
        with service.running(program) as run:
            result = run.result(timeout_s=1)

    assert not result.iq_by_adc
    names = [call[0] for call in backend.calls]
    assert names.count("sys_run_level1_trigger") == 2
    assert names.count("sys_wait_until_finish") == 1


def test_wait_failure_cleans_up_and_allows_another_run():
    backend = FakeMmcsBackend(fail_method="sys_wait_until_finish")
    _, service = make_service(backend)
    program = make_program(adc_programs=())

    with service.connected():
        with pytest.raises(InstrumentCommandError):
            with service.running(program) as run:
                run.result(timeout_s=1)
        backend.fail_method = None
        with service.running(program):
            pass


def test_start_failure_cleans_up_without_entering_body():
    backend = FakeMmcsBackend(fail_method="sys_run_level1_trigger")
    _, service = make_service(backend)
    entered = False

    with service.connected():
        with pytest.raises(InstrumentCommandError):
            with service.running(make_program(adc_programs=())):
                entered = True
    assert not entered
    names = [call[0] for call in backend.calls]
    assert names.count("sys_clear_all_level2_trigger_ram") >= 2


def test_prepare_failure_cleans_up_without_entering_body():
    backend = FakeMmcsBackend(fail_method="da_set_multi_waveform")
    _, service = make_service(backend)
    entered = False
    with service.connected():
        with pytest.raises(InstrumentCommandError):
            with service.running(make_program()):
                entered = True
    assert not entered


@pytest.mark.parametrize(
    ("fail_method", "fail_call_number"),
    [
        ("da_clear_wave_ram", None),
        ("da_set_multi_waveform", 2),
        ("da_set_level2_trigger_ram", None),
    ],
)
def test_each_board_prepare_stage_failure_prevents_start_and_cleans_up(
    fail_method, fail_call_number
):
    backend = FakeMmcsBackend(
        fail_method=fail_method,
        fail_call_number=fail_call_number,
    )
    _, service = make_service(backend)
    with service.connected():
        with pytest.raises(InstrumentCommandError):
            with service.running(make_program(adc_programs=())):
                pytest.fail("failed prepare must not enter the run body")
    names = [call[0] for call in backend.calls]
    assert "sys_run_level1_trigger" not in names
    assert names.count("sys_clear_all_level2_trigger_ram") >= 2


def test_connection_and_running_guards_and_stale_handle():
    backend = FakeMmcsBackend()
    _, service = make_service(backend)
    program = make_program(adc_programs=())

    with pytest.raises(InstrumentStateError, match="connected"):
        with service.running(program):
            pass

    with service.connected():
        with pytest.raises(InstrumentStateError, match="already connected"):
            with service.connected():
                pass
        with service.running(program) as stale:
            with pytest.raises(InstrumentStateError, match="already running"):
                with service.running(program):
                    pass
    with pytest.raises(InstrumentStateError, match="connected"):
        stale.result(timeout_s=1)


def test_status_check_requires_connection_and_forwards_response():
    backend = FakeMmcsBackend()
    _, service = make_service(backend)

    with pytest.raises(InstrumentStateError, match="connected"):
        service.check_status()

    with service.connected():
        assert service.check_status() == 0

    assert [call[0] for call in backend.calls].count("sys_get_fpga_version") == 1


def test_body_error_is_preserved_when_stop_also_fails():
    backend = FakeMmcsBackend()
    _, service = make_service(backend)
    with pytest.raises(ValueError, match="primary") as captured:
        with service.connected():
            with service.running(make_program(adc_programs=())):
                backend.fail_method = "sys_stop_all_borad"
                raise ValueError("primary")
    assert any("Stopping MMCS also failed" in note for note in captured.value.__notes__)


def tone_spec(**changes):
    values = dict(
        sample_rate_hz=2e9,
        frequency_hz=23e6,
        amplitude=0.1,
        phase_rad=0.25,
        minimum_samples=801,
    )
    values.update(changes)
    return SingleToneSpec(**values)


def test_generate_single_tone_is_aligned_bounded_and_periodic():
    tone = generate_single_tone(tone_spec())
    samples = tone.waveform.samples
    assert samples.size >= 801 and samples.size % 8 == 0
    assert np.max(np.abs(samples)) <= 0.1 + 1e-12
    cycles = tone.actual_frequency_hz * samples.size / tone.spec.sample_rate_hz
    assert cycles == pytest.approx(round(cycles))
    first_after_repeat = 0.1 * np.sin(2 * np.pi * cycles + 0.25)
    assert first_after_repeat == pytest.approx(samples[0])
    assert abs(tone.actual_frequency_hz - 23e6) <= tone.spec.sample_rate_hz / samples.size / 2


def iq_tone_spec(**changes):
    values = dict(
        sample_rate_hz=2e9,
        if_frequency_hz=20e6,
        amplitude=0.1,
        phase_rad=0.0,
        minimum_samples=800,
        sideband=Sideband.UPPER,
        calibration=IqCalibration(),
    )
    values.update(changes)
    return IqToneSpec(**values)


def test_generate_iq_tone_is_shared_periodic_pair_and_sideband_flips_q_only():
    upper = generate_iq_tone(iq_tone_spec())
    lower = generate_iq_tone(iq_tone_spec(sideband=Sideband.LOWER))

    assert upper.actual_if_frequency_hz == 20e6
    assert upper.i_waveform.samples.size == upper.q_waveform.samples.size == 800
    np.testing.assert_allclose(upper.i_waveform.samples, lower.i_waveform.samples)
    np.testing.assert_allclose(upper.q_waveform.samples, -lower.q_waveform.samples)
    assert upper.i_waveform.samples[0] == pytest.approx(0.1)
    assert upper.q_waveform.samples[0] == pytest.approx(0.0)


def test_generate_iq_tone_applies_calibration_formula():
    calibration = IqCalibration(
        q_over_i_gain=1.5,
        i_offset=0.1,
        q_offset=-0.2,
        q_phase_correction_rad=np.pi / 2,
    )
    tone = generate_iq_tone(iq_tone_spec(amplitude=0.1, calibration=calibration))
    assert tone.i_waveform.samples[0] == pytest.approx(0.2)
    assert tone.q_waveform.samples[0] == pytest.approx(-0.05)


def test_generate_iq_tone_rejects_calibrated_overflow():
    with pytest.raises(ValueError, match="exceeds"):
        generate_iq_tone(
            iq_tone_spec(
                amplitude=1.0,
                calibration=IqCalibration(i_offset=0.1),
            )
        )


@pytest.mark.parametrize(
    "calibration",
    [
        {"q_over_i_gain": 0.0},
        {"q_over_i_gain": -1.0},
        {"i_offset": 1.1},
        {"q_phase_correction_rad": np.nan},
    ],
)
def test_invalid_iq_calibration_is_rejected(calibration):
    with pytest.raises(PydanticValidationError):
        IqCalibration(**calibration)


@pytest.mark.parametrize(
    "changes",
    [
        {"sample_rate_hz": 0},
        {"frequency_hz": 1e9},
        {"frequency_hz": np.nan},
        {"amplitude": 0},
        {"amplitude": 1.1},
        {"minimum_samples": 7},
    ],
)
def test_invalid_single_tone_is_rejected(changes):
    with pytest.raises(PydanticValidationError):
        tone_spec(**changes)


def test_build_cyclic_dac_program():
    tone = generate_single_tone(
        tone_spec(frequency_hz=20e6, amplitude=0.02, phase_rad=0, minimum_samples=800)
    )
    program = build_cyclic_dac_program(
        tone.waveform,
        board_id="da_box1pcie1ch12",
        channel=DacChannel.I,
        master_box="box1",
        run_duration_s=0.003,
        period_ns=1_000_000,
        start_trigger_ns=40,
    )
    board = program.dac_boards[0]
    assert not program.adc_programs
    assert program.repetitions == 3
    assert {channel.channel for channel in board.channels} == {DacChannel.I, DacChannel.Q}
    assert all(channel.play_mode is DacPlayMode.CYCLE for channel in board.channels)
    assert np.all(board.channels[1].waveforms[0].samples == 0)
    assert [event.command for event in board.triggers] == [
        TriggerCommand.START,
        TriggerCommand.STOP,
    ]


def test_build_iq_upconversion_program_uses_generated_pair():
    tone = generate_iq_tone(iq_tone_spec())
    program = build_iq_upconversion_program(
        tone,
        board_id="da_box1pcie1ch12",
        master_box="box1",
        run_duration_s=0.003,
        period_ns=1_000_000,
        start_trigger_ns=40,
    )
    channels = {channel.channel: channel for channel in program.dac_boards[0].channels}
    np.testing.assert_array_equal(
        channels[DacChannel.I].waveforms[0].samples, tone.i_waveform.samples
    )
    np.testing.assert_array_equal(
        channels[DacChannel.Q].waveforms[0].samples, tone.q_waveform.samples
    )


def test_dac_board_requires_unique_iq_pair_and_matching_channel_structure():
    program = make_program(adc_programs=())
    board = program.dac_boards[0]
    with pytest.raises(PydanticValidationError, match="must declare I and Q"):
        MmcsProgram(
            master_box="box1",
            period_ns=100,
            repetitions=1,
            dac_boards=(board.model_copy(update={"channels": (board.channels[0],)}),),
        )
    with pytest.raises(PydanticValidationError, match="duplicate channels"):
        MmcsProgram(
            master_box="box1",
            period_ns=100,
            repetitions=1,
            dac_boards=(
                board.model_copy(update={"channels": (board.channels[0], board.channels[0])}),
            ),
        )
    mismatched_q = board.channels[1].model_copy(
        update={"waveforms": (DacWaveform(samples=np.zeros(16)),)}
    )
    with pytest.raises(PydanticValidationError, match="equal lengths"):
        MmcsProgram(
            master_box="box1",
            period_ns=100,
            repetitions=1,
            dac_boards=(
                board.model_copy(update={"channels": (board.channels[0], mismatched_q)}),
            ),
        )


def test_dac_board_id_is_unique_and_fingerprint_covers_board_state():
    program = make_program(adc_programs=())
    board = program.dac_boards[0]
    with pytest.raises(PydanticValidationError, match="Duplicate or empty DAC board"):
        MmcsProgram(
            master_box="box1",
            period_ns=100,
            repetitions=1,
            dac_boards=(board, board),
        )

    changed_q = board.channels[1].model_copy(
        update={"waveforms": (DacWaveform(samples=np.ones(8) * 0.1),)}
    )
    changed = MmcsProgram(
        master_box="box1",
        period_ns=100,
        repetitions=1,
        dac_boards=(board.model_copy(update={"channels": (board.channels[0], changed_q)}),),
    )
    assert changed.fingerprint() != program.fingerprint()


def test_service_prepares_board_channels_then_configures_one_trigger_and_cleans_up():
    backend = FakeMmcsBackend()
    _, service = make_service(backend)
    with service.connected():
        with service.running(make_program(adc_programs=())) as run:
            run.result(timeout_s=1)
        names = [call[0] for call in backend.calls]

    expected = [
        "sys_stop_all_borad",
        "sys_clear_all_level2_trigger_ram",
        "da_clear_wave_ram",
        "da_set_multi_waveform",
        "da_set_multi_waveform",
        "da_set_level2_trigger_ram",
        "sys_set_level1_trigger",
        "sys_run_level1_trigger",
        "sys_wait_until_finish",
        "sys_stop_all_borad",
        "sys_clear_all_level2_trigger_ram",
    ]
    assert names[: len(expected)] == expected
    assert names[: len(expected)].count("da_set_level2_trigger_ram") == 1


def invalid_waveform_program():
    waveform = DacWaveform(samples=np.zeros(7))
    playlist = (PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),)
    board = DacBoardProgram(
        board_id="da",
        triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
        channels=tuple(
            DacChannelProgram(
                channel=channel,
                waveforms=(waveform,),
                playlist=playlist,
                play_mode=DacPlayMode.END_WITH_ZERO,
            )
            for channel in DacChannel
        ),
    )
    return make_program(dac_boards=(board,))


def invalid_demodulation_program():
    adc = AdcProgram(
        board_id="ad",
        sample_length=8,
        demodulations=(DemodulationWeights(channel=12, i=np.zeros(8), q=np.zeros(8)),),
        triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
    )
    return make_program(adc_programs=(adc,))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: make_program(repetitions=0),
        lambda: make_program(period_ns=101),
        invalid_waveform_program,
        invalid_demodulation_program,
        lambda: make_program(
            adc_programs=(
                AdcProgram(
                    board_id="ad",
                    sample_length=8,
                    demodulations=(),
                    triggers=(TriggerEvent(time_ns=100, command=TriggerCommand.START),),
                ),
            )
        ),
    ],
)
def test_program_validation_occurs_at_construction(factory):
    with pytest.raises(PydanticValidationError):
        factory()


def test_vendor_transport_close_is_idempotent():
    backend = FakeMmcsBackend()
    transport = MmcsVendorTransport(
        {"box1": "192.0.2.1"}, backend_factory=lambda boxes: backend
    )
    transport.open()
    transport.close()
    transport.close()
    assert backend.closed
    assert [call[0] for call in backend.calls].count("sys_close") == 1
