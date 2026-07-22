from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError as PydanticValidationError

from control.application import MmcsExecutor
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
    build_cyclic_dac_program,
    generate_single_tone,
)
from control.driver.mmcs import MmcsHardwareDriver
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


def make_stack(backend):
    transport = MmcsVendorTransport(
        {"box1": "192.0.2.1"}, backend_factory=lambda boxes: backend
    )
    driver = MmcsHardwareDriver(transport, shutdown_timeout_s=5)
    driver.connect()
    return transport, driver, MmcsExecutor(driver, cleanup_timeout_s=5)


def test_prepare_run_and_reuse_program():
    backend = FakeMmcsBackend()
    _, _, executor = make_stack(backend)
    executor.prepare(make_program())

    executor.start()
    first = executor.wait(timeout_s=2)
    executor.start()
    second = executor.wait(timeout_s=2)

    assert set(first.iq_by_adc) == {"ad_box1pcie1ch12"}
    assert first.iq_by_adc["ad_box1pcie1ch12"].i_sum.shape == (12, 2)
    assert first.program_fingerprint == second.program_fingerprint
    names = [call[0] for call in backend.calls]
    assert names.count("da_set_multi_waveform") == 1
    assert names.count("sys_run_level1_trigger") == 2
    assert names.count("ad_clear_stored_data") == 3
    with pytest.raises(ValueError):
        first.iq_by_adc["ad_box1pcie1ch12"].i_sum[0, 0] = 1


def test_start_wait_stop_lifecycle():
    backend = FakeMmcsBackend()
    _, _, executor = make_stack(backend)
    executor.prepare(make_program(adc_programs=()))

    executor.start()
    with pytest.raises(InstrumentStateError, match="already running"):
        executor.start()
    executor.stop()

    executor.start()
    result = executor.wait(timeout_s=1)
    assert not result.iq_by_adc
    names = [call[0] for call in backend.calls]
    assert names.count("sys_run_level1_trigger") == 2
    assert names.count("sys_wait_until_finish") == 1


def test_wait_failure_cleans_up_and_releases_executor():
    backend = FakeMmcsBackend(fail_method="sys_wait_until_finish")
    _, _, executor = make_stack(backend)
    executor.prepare(make_program(adc_programs=()))
    executor.start()

    with pytest.raises(InstrumentCommandError):
        executor.wait(timeout_s=1)
    with pytest.raises(InstrumentStateError, match="not running"):
        executor.stop()


def test_start_failure_cleans_up_and_releases_executor():
    backend = FakeMmcsBackend(fail_method="sys_run_level1_trigger")
    _, _, executor = make_stack(backend)
    executor.prepare(make_program(adc_programs=()))

    with pytest.raises(InstrumentCommandError):
        executor.start()
    executor.prepare(make_program(adc_programs=()))
    names = [call[0] for call in backend.calls]
    assert names.count("sys_stop_all_borad") >= 3


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
    tone = generate_single_tone(tone_spec(frequency_hz=20e6, amplitude=0.02, phase_rad=0, minimum_samples=800))
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


def test_prepared_program_invalid_after_reconnect():
    backends = []

    def factory(boxes):
        backend = FakeMmcsBackend()
        backends.append(backend)
        return backend

    transport = MmcsVendorTransport({"box1": "192.0.2.1"}, backend_factory=factory)
    driver = MmcsHardwareDriver(transport, shutdown_timeout_s=5)
    driver.connect()
    executor = MmcsExecutor(driver, cleanup_timeout_s=5)
    executor.prepare(make_program())
    driver.close()
    driver.connect()

    with pytest.raises(InstrumentStateError, match="invalid after reconnect"):
        executor.start()


def test_prepare_failure_runs_cleanup_and_preserves_primary_error():
    backend = FakeMmcsBackend(fail_method="da_set_multi_waveform")
    _, _, executor = make_stack(backend)
    with pytest.raises(InstrumentCommandError):
        executor.prepare(make_program())
    names = [call[0] for call in backend.calls]
    assert names.count("sys_stop_all_borad") >= 2
    assert names.count("sys_clear_all_level2_trigger_ram") >= 2


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
