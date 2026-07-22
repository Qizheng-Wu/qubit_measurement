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
                (PlaylistEntry(0),),
                DacPlayMode.END_WITH_ZERO,
                (TriggerEvent(40),),
            ),
        ),
        adc_programs=(
            AdcProgram(
                "ad_box1pcie1ch12",
                8,
                (weights,),
                (TriggerEvent(40),),
            ),
        ),
    )
    values.update(changes)
    return MmcsProgram(**values)


def make_stack(backend):
    transport = MmcsVendorTransport(
        {"box1": "192.0.2.1"}, backend_factory=lambda boxes: backend
    )
    driver = MmcsHardwareDriver(transport)
    driver.connect()
    return transport, driver, MmcsExecutor(driver)


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


def test_prepared_program_invalid_after_reconnect():
    backends = []

    def factory(boxes):
        backend = FakeMmcsBackend()
        backends.append(backend)
        return backend

    transport = MmcsVendorTransport({"box1": "192.0.2.1"}, backend_factory=factory)
    driver = MmcsHardwareDriver(transport)
    driver.connect()
    executor = MmcsExecutor(driver)
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
                    (PlaylistEntry(0),),
                    DacPlayMode.END_WITH_ZERO,
                    (TriggerEvent(40),),
                ),
            )
        ),
        make_program(
            adc_programs=(
                AdcProgram(
                    "ad",
                    8,
                    (DemodulationWeights(12, np.zeros(8), np.zeros(8)),),
                    (TriggerEvent(40),),
                ),
            )
        ),
        make_program(
            adc_programs=(
                AdcProgram(
                    "ad",
                    8,
                    (),
                    (TriggerEvent(100),),
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
