from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError as PydanticValidationError

from control.core.exceptions import InstrumentCommandError, InstrumentStateError
from control.domain.mmcs import (
    AdcProgram,
    DacChannel,
    DacPlayMode,
    DacProgram,
    DacWaveform,
    DemodulationWeights,
    MmcsProgram,
    PlaylistEntry,
    SingleToneSpec,
    TriggerCommand,
    TriggerEvent,
)
from control.driver.mmcs import MmcsHardwareDriver
from control.services import MmcsService, build_cyclic_dac_program, generate_single_tone
from control.transport.mmcs_vendor import MmcsVendorTransport


class FakeMmcsBackend:
    def __init__(self, *, fail_method=None):
        self.calls = []
        self.fail_method = fail_method
        self.closed = False

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == self.fail_method:
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
    weights = DemodulationWeights(channel=0, i=np.zeros(8), q=np.zeros(8))
    values = dict(
        master_box="box1",
        period_ns=100,
        repetitions=2,
        dac_programs=(
            DacProgram(
                board_id="da_box1pcie1ch12",
                channel=DacChannel.I,
                waveforms=(waveform,),
                playlist=(PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),),
                play_mode=DacPlayMode.END_WITH_ZERO,
                triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
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
    assert names.count("da_set_multi_waveform") == 2
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
    dac = program.dac_programs[0]
    assert not program.adc_programs
    assert program.repetitions == 3
    assert dac.play_mode is DacPlayMode.CYCLE
    assert [event.command for event in dac.triggers] == [
        TriggerCommand.START,
        TriggerCommand.STOP,
    ]


def invalid_waveform_program():
    dac = DacProgram(
        board_id="da",
        channel=DacChannel.I,
        waveforms=(DacWaveform(samples=np.zeros(7)),),
        playlist=(PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),),
        play_mode=DacPlayMode.END_WITH_ZERO,
        triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
    )
    return make_program(dac_programs=(dac,))


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
