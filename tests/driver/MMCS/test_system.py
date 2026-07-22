from __future__ import annotations

import numpy as np
import pytest

from control.driver.MMCS import (
    BoxConfig,
    DacAddress,
    DacPair,
    DacSequence,
    HardwareCommandError,
    MmcsSystem,
    SystemState,
    TimeoutError,
    TriggerEvent,
    TriggerProgram,
    ValidationError,
    WaveSegment,
)

from .fakes import FakeBackend


BOXES = (BoxConfig("box1", "192.168.4.8"), BoxConfig("box2", "192.168.4.9"))
DAC1 = DacAddress("box1", 3, DacPair.CH12)
DAC2 = DacAddress("box2", 2, DacPair.CH34)


def ready_system(backend: FakeBackend | None = None):
    backend = backend or FakeBackend((DAC1, DAC2))
    system = MmcsSystem(BOXES, backend=backend)
    inventory = system.connect()
    system.initialize_safe(master_box="box1")
    return system, backend, inventory


def test_multibox_discovery_and_safe_initialization_order() -> None:
    system, backend, inventory = ready_system()
    assert inventory.dacs == (DAC1, DAC2)
    assert system.state is SystemState.SAFE
    assert [call[0] for call in backend.calls[:3]] == [
        "connect",
        "stop_all",
        "clear_trigger_memory",
    ]


def test_single_upload_execute_and_close_are_ordered() -> None:
    system, backend, _ = ready_system()
    dac = system.dac(DAC1)
    dac.upload_iq(np.zeros(8), np.ones(8) * 0.1)
    program = TriggerProgram.single(
        dac=DAC1,
        trigger_ns=40,
        period_ns=10_000,
        repetitions=5,
        master_box="box1",
    )
    system.execute(program, timeout_s=2)
    assert system.state is SystemState.ARMED
    names = [call[0] for call in backend.calls]
    assert names[3:10] == [
        "upload_single",
        "upload_single",
        "clear_trigger_memory",
        "set_dac_triggers",
        "set_level1",
        "run",
        "wait",
    ]
    system.close()
    system.close()
    assert system.state is SystemState.CLOSED
    assert names.count("close") == 0
    assert [call[0] for call in backend.calls].count("close") == 1


def test_multi_segment_requires_one_start_per_segment() -> None:
    system, backend, _ = ready_system()
    sequence = DacSequence(
        (
            WaveSegment(np.zeros(8), np.zeros(8)),
            WaveSegment(np.ones(8) * 0.1, np.ones(8) * -0.1),
        )
    )
    system.dac(DAC1).upload_sequence(sequence)
    bad = TriggerProgram(100, 1, "box1", {DAC1: (TriggerEvent(4),)})
    with pytest.raises(ValidationError, match="2 uploaded"):
        system.arm(bad)
    good = TriggerProgram(
        100,
        1,
        "box1",
        {DAC1: (TriggerEvent(4), TriggerEvent(8))},
    )
    system.arm(good)
    assert system.state is SystemState.ARMED
    uploads = [call for call in backend.calls if call[0] == "upload_sequence"]
    assert len(uploads) == 2
    assert all(len(call[3]) == 2 for call in uploads)


def test_partial_iq_upload_failure_faults_and_stops() -> None:
    class FailQBackend(FakeBackend):
        def upload_single(self, address, lane, wave, mode):
            super().upload_single(address, lane, wave, mode)
            if lane.value == "q":
                raise RuntimeError("Q upload failed")

    backend = FailQBackend((DAC1,))
    system, backend, _ = ready_system(backend)
    with pytest.raises(HardwareCommandError, match="waveform upload failed"):
        system.dac(DAC1).upload_iq(np.zeros(8), np.zeros(8))
    assert system.state is SystemState.FAULTED
    assert [call[0] for call in backend.calls[-2:]] == ["stop_all", "clear_trigger_memory"]


def test_multibox_upload_failure_uses_initialized_master_box() -> None:
    backend = FakeBackend((DAC2,))
    backend.fail_on = "upload_single"
    system, backend, _ = ready_system(backend)
    with pytest.raises(HardwareCommandError):
        system.dac(DAC2).upload_iq(np.zeros(8), np.zeros(8))
    stop = [call for call in backend.calls if call[0] == "stop_all"][-1]
    assert stop[1] == "box1"


def test_wait_timeout_preserves_timeout_type_and_faults() -> None:
    class TimeoutBackend(FakeBackend):
        def wait(self, master_box: str, timeout_s: float) -> None:
            super().wait(master_box, timeout_s)
            raise TimeoutError("injected timeout")

    backend = TimeoutBackend((DAC1,))
    system, _, _ = ready_system(backend)
    system.dac(DAC1).upload_iq(np.zeros(8), np.zeros(8))
    program = TriggerProgram.single(
        dac=DAC1,
        trigger_ns=4,
        period_ns=100,
        repetitions=1,
        master_box="box1",
    )
    with pytest.raises(TimeoutError, match="injected timeout"):
        system.execute(program, timeout_s=0.01)
    assert system.state is SystemState.FAULTED


def test_context_does_not_mask_active_exception_with_cleanup_failure() -> None:
    backend = FakeBackend((DAC1,))
    backend.fail_on = "stop_all"
    with pytest.raises(RuntimeError, match="business failure"):
        with MmcsSystem((BOXES[0],), backend=backend) as system:
            system.connect()
            raise RuntimeError("business failure")
    assert system.state is SystemState.CLOSED


def test_invalid_state_operations_fail() -> None:
    system = MmcsSystem((BOXES[0],), backend=FakeBackend((DAC1,)))
    with pytest.raises(HardwareCommandError):
        system.dac(DAC1)
    with pytest.raises(HardwareCommandError):
        system.execute(
            TriggerProgram.single(
                dac=DAC1,
                trigger_ns=4,
                period_ns=100,
                repetitions=1,
                master_box="box1",
            ),
            timeout_s=1,
        )


def test_run_rejects_master_box_different_from_armed_program() -> None:
    system, _, _ = ready_system()
    system.dac(DAC1).upload_iq(np.zeros(8), np.zeros(8))
    system.arm(
        TriggerProgram.single(
            dac=DAC1,
            trigger_ns=4,
            period_ns=100,
            repetitions=1,
            master_box="box1",
        )
    )
    with pytest.raises(ValidationError, match="armed for"):
        system.run(master_box="box2")
