from __future__ import annotations

import numpy as np
import pytest

from control.core.exceptions import InstrumentCommandError, InstrumentStateError, ValidationError
from control.domain.mmcs import (
    AdcProgram,
    DacChannel,
    DacPlayMode,
    DacProgram,
    DacWaveform,
    DemodulationWeights,
    MmcsExecutor,
    MmcsProgram,
    PlaylistEntry,
    TriggerCommand,
    TriggerEvent,
    SingleToneSpec,
    build_cyclic_dac_program,
    generate_single_tone,
    validate_program,
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
    waveform = DacWaveform(np.zeros(8))
    weights = DemodulationWeights(0, np.zeros(8), np.zeros(8))
    values = dict(
        master_box="box1",
        period_ns=100,
        repetitions=2,
        dac_programs=(
            DacProgram(
                "da_box1pcie1ch12",
                DacChannel.I,
                (waveform,),
                (PlaylistEntry(0, TriggerCommand.START),),
                DacPlayMode.END_WITH_ZERO,
                (TriggerEvent(40, TriggerCommand.START),),
            ),
        ),
        adc_programs=(
            AdcProgram(
                "ad_box1pcie1ch12",
                8,
                (weights,),
                (TriggerEvent(40, TriggerCommand.START),),
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
    transport, driver, executor = make_stack(backend)
    prepared = executor.prepare(make_program())

    first = executor.run(prepared, timeout_s=2)
    second = executor.run(prepared, timeout_s=2)

    assert set(first.iq_by_adc) == {"ad_box1pcie1ch12"}
    assert first.iq_by_adc["ad_box1pcie1ch12"].i_sum.shape == (12, 2)
    assert first.program_fingerprint == second.program_fingerprint
    names = [call[0] for call in backend.calls]
    assert names.count("da_set_multi_waveform") == 1
    assert names.count("sys_run_level1_trigger") == 2
    assert names.count("ad_clear_stored_data") == 3  # prepare plus each run
    with pytest.raises(ValueError):
        first.iq_by_adc["ad_box1pcie1ch12"].i_sum[0, 0] = 1


def test_start_wait_stop_lifecycle():
    backend = FakeMmcsBackend()
    _, _, executor = make_stack(backend)
    prepared = executor.prepare(make_program(adc_programs=()))

    running = executor.start(prepared)
    with pytest.raises(InstrumentStateError, match="already running"):
        executor.start(prepared)
    executor.stop(running)

    second = executor.start(prepared)
    result = executor.wait(second, timeout_s=1)
    assert not result.iq_by_adc
    names = [call[0] for call in backend.calls]
    assert names.count("sys_run_level1_trigger") == 2
    assert names.count("sys_wait_until_finish") == 1


def test_wait_failure_cleans_up_and_releases_executor():
    backend = FakeMmcsBackend(fail_method="sys_wait_until_finish")
    _, _, executor = make_stack(backend)
    prepared = executor.prepare(make_program(adc_programs=()))
    running = executor.start(prepared)

    with pytest.raises(InstrumentCommandError):
        executor.wait(running, timeout_s=1)
    with pytest.raises(InstrumentStateError, match="not active"):
        executor.stop(running)


def test_start_failure_cleans_up_and_releases_executor():
    backend = FakeMmcsBackend(fail_method="sys_run_level1_trigger")
    _, _, executor = make_stack(backend)
    prepared = executor.prepare(make_program(adc_programs=()))

    with pytest.raises(InstrumentCommandError):
        executor.start(prepared)
    executor.prepare(make_program(adc_programs=()))
    names = [call[0] for call in backend.calls]
    assert names.count("sys_stop_all_borad") >= 3


def test_generate_single_tone_is_aligned_bounded_and_periodic():
    tone = generate_single_tone(SingleToneSpec(2e9, 23e6, 0.1, 0.25, 801))
    samples = tone.waveform.samples
    assert samples.size >= 801 and samples.size % 8 == 0
    assert np.max(np.abs(samples)) <= 0.1 + 1e-12
    cycles = tone.actual_frequency_hz * samples.size / tone.spec.sample_rate_hz
    assert cycles == pytest.approx(round(cycles))
    first_after_repeat = 0.1 * np.sin(2 * np.pi * cycles + 0.25)
    assert first_after_repeat == pytest.approx(samples[0])
    assert abs(tone.actual_frequency_hz - 23e6) <= tone.spec.sample_rate_hz / samples.size / 2


@pytest.mark.parametrize(
    "spec",
    [
        lambda: SingleToneSpec(0, 1, 0.1, 0, 800),
        lambda: SingleToneSpec(2e9, 1e9, 0.1, 0, 800),
        lambda: SingleToneSpec(2e9, np.nan, 0.1, 0, 800),
        lambda: SingleToneSpec(2e9, 20e6, 0, 0, 800),
        lambda: SingleToneSpec(2e9, 20e6, 1.1, 0, 800),
        lambda: SingleToneSpec(2e9, 20e6, 0.1, 0, 7),
    ],
)
def test_invalid_single_tone_is_rejected(spec):
    with pytest.raises(ValidationError):
        spec()


def test_build_cyclic_dac_program():
    tone = generate_single_tone(SingleToneSpec(2e9, 20e6, 0.02, 0, 800))
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
    prepared = executor.prepare(make_program())
    driver.close()
    driver.connect()

    with pytest.raises(InstrumentStateError):
        executor.run(prepared, timeout_s=1)


def test_prepare_failure_runs_cleanup_and_preserves_primary_error():
    backend = FakeMmcsBackend(fail_method="da_set_multi_waveform")
    _, _, executor = make_stack(backend)
    with pytest.raises(InstrumentCommandError):
        executor.prepare(make_program())
    names = [call[0] for call in backend.calls]
    assert names.count("sys_stop_all_borad") >= 2
    assert names.count("sys_clear_all_level2_trigger_ram") >= 2


@pytest.mark.parametrize(
    "program",
    [
        make_program(repetitions=0),
        make_program(period_ns=101),
        make_program(
            dac_programs=(
                DacProgram(
                    "da",
                    DacChannel.I,
                    (DacWaveform(np.zeros(7)),),
                    (PlaylistEntry(0, TriggerCommand.START),),
                    DacPlayMode.END_WITH_ZERO,
                    (TriggerEvent(40, TriggerCommand.START),),
                ),
            )
        ),
        make_program(
            adc_programs=(
                AdcProgram(
                    "ad",
                    8,
                    (DemodulationWeights(12, np.zeros(8), np.zeros(8)),),
                    (TriggerEvent(40, TriggerCommand.START),),
                ),
            )
        ),
        make_program(
            adc_programs=(
                AdcProgram(
                    "ad",
                    8,
                    (),
                    (TriggerEvent(100, TriggerCommand.START),),
                ),
            )
        ),
    ],
)
def test_program_validation(program):
    with pytest.raises(ValidationError):
        validate_program(program)


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
