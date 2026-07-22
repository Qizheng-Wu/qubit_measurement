from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from control.core.exceptions import AcquisitionError
from control.core.identity import InstrumentIdentity
from control.domain.mmcs import (
    DacChannel,
    SingleToneSpec,
    build_cyclic_dac_program,
    generate_single_tone,
)
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace
from experiment.mmcs_awg_spectrum import acquire_spectrum_while_mmcs_runs


def make_trace() -> SpectrumTrace:
    config = SpectrumSweepConfig(10e6, 30e6, 5, 100e3, 20)
    return SpectrumTrace(
        frequency_hz=np.linspace(10e6, 30e6, 5),
        power_dbm=np.array([-90, -80, -35, -82, -91]),
        config=config,
        instrument=InstrumentIdentity("R&S", "FPL", "1", "1", "R&S,FPL,1,1"),
        acquired_at=datetime.now(timezone.utc),
    )


def make_program():
    tone = generate_single_tone(SingleToneSpec(2e9, 20e6, 0.02))
    return build_cyclic_dac_program(
        tone.waveform,
        board_id="da",
        channel=DacChannel.I,
        master_box="box1",
        run_duration_s=1,
    )


class FakeExecutor:
    def __init__(self, events, *, fail_stop=False):
        self.events = events
        self.fail_stop = fail_stop

    def prepare(self, program):
        self.events.append("prepare")
        return program

    def start(self, prepared):
        self.events.append("start")
        return prepared

    def stop(self, running):
        self.events.append("stop")
        if self.fail_stop:
            raise RuntimeError("injected stop failure")


class FakeAnalyzer:
    def __init__(self, events, *, fail=False):
        self.events = events
        self.fail = fail

    def acquire(self, config, *, timeout_s):
        self.events.append("acquire")
        if self.fail:
            raise AcquisitionError("injected acquisition failure")
        return make_trace()


def test_spectrum_is_acquired_between_mmcs_start_and_stop():
    events = []
    trace = acquire_spectrum_while_mmcs_runs(
        FakeExecutor(events),
        FakeAnalyzer(events),
        program=make_program(),
        spectrum_config=make_trace().config,
        spectrum_timeout_s=1,
    )
    assert events == ["prepare", "start", "acquire", "stop"]
    assert trace.power_dbm[2] == -35


def test_analyzer_failure_still_stops_mmcs():
    events = []
    with pytest.raises(AcquisitionError, match="injected acquisition"):
        acquire_spectrum_while_mmcs_runs(
            FakeExecutor(events),
            FakeAnalyzer(events, fail=True),
            program=make_program(),
            spectrum_config=make_trace().config,
            spectrum_timeout_s=1,
        )
    assert events == ["prepare", "start", "acquire", "stop"]


def test_stop_failure_is_reported_after_successful_acquisition():
    with pytest.raises(AcquisitionError, match="stopping MMCS"):
        acquire_spectrum_while_mmcs_runs(
            FakeExecutor([], fail_stop=True),
            FakeAnalyzer([]),
            program=make_program(),
            spectrum_config=make_trace().config,
            spectrum_timeout_s=1,
        )


def test_acquisition_error_remains_primary_when_stop_also_fails():
    with pytest.raises(AcquisitionError, match="injected acquisition") as caught:
        acquire_spectrum_while_mmcs_runs(
            FakeExecutor([], fail_stop=True),
            FakeAnalyzer([], fail=True),
            program=make_program(),
            spectrum_config=make_trace().config,
            spectrum_timeout_s=1,
        )
    assert any("Stopping MMCS output also failed" in note for note in caught.value.__notes__)
