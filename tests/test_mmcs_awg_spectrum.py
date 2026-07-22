import pytest

from control.application import acquire_spectrum_while_mmcs_runs
from control.core.exceptions import AcquisitionError


class FakeExecutor:
    def __init__(self, events, *, fail_stop=False):
        self.events = events
        self.fail_stop = fail_stop

    def prepare(self, program):
        self.events.append("prepare")

    def start(self):
        self.events.append("start")

    def stop(self):
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
        return "trace"


def test_acquisition_occurs_between_start_and_stop():
    events = []
    trace = acquire_spectrum_while_mmcs_runs(
        FakeExecutor(events),
        FakeAnalyzer(events),
        program=object(),
        spectrum_config=object(),
        spectrum_timeout_s=1,
    )
    assert events == ["prepare", "start", "acquire", "stop"]
    assert trace == "trace"


def test_acquisition_failure_still_stops():
    events = []
    with pytest.raises(AcquisitionError, match="injected acquisition"):
        acquire_spectrum_while_mmcs_runs(
            FakeExecutor(events),
            FakeAnalyzer(events, fail=True),
            program=object(),
            spectrum_config=object(),
            spectrum_timeout_s=1,
        )
    assert events == ["prepare", "start", "acquire", "stop"]


def test_stop_failure_is_reported():
    events = []
    with pytest.raises(RuntimeError, match="stop failure"):
        acquire_spectrum_while_mmcs_runs(
            FakeExecutor(events, fail_stop=True),
            FakeAnalyzer(events),
            program=object(),
            spectrum_config=object(),
            spectrum_timeout_s=1,
        )
    assert events == ["prepare", "start", "acquire", "stop"]
