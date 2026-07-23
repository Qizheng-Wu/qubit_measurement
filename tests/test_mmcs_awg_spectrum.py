from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from control.core.exceptions import AcquisitionError
from experiment.config import DEFAULT_CONFIG_PATH, load_config
from experiment.mmcs_awg_spectrum import run_experiment


class FakeMmcsService:
    def __init__(self, events):
        self.events = events

    @contextmanager
    def connected(self):
        self.events.append("mmcs-connect")
        try:
            yield self
        finally:
            self.events.append("mmcs-disconnect")

    @contextmanager
    def running(self, program):
        self.events.append("mmcs-start")
        try:
            yield object()
        finally:
            self.events.append("mmcs-stop")


class FakeSpectrumRun:
    def __init__(self, events, *, fail):
        self.events = events
        self.fail = fail

    def result(self, *, timeout_s):
        self.events.append("spectrum-result")
        if self.fail:
            raise AcquisitionError("injected acquisition failure")
        return "trace"


class FakeSpectrumService:
    def __init__(self, events, *, fail=False):
        self.events = events
        self.fail = fail

    @contextmanager
    def connected(self):
        self.events.append("spectrum-connect")
        try:
            yield self
        finally:
            self.events.append("spectrum-disconnect")

    @contextmanager
    def running(self, config):
        self.events.append("spectrum-start")
        try:
            yield FakeSpectrumRun(self.events, fail=self.fail)
        finally:
            self.events.append("spectrum-stop")


def make_plan():
    return SimpleNamespace(
        mmcs_program=object(),
        spectrum_config=object(),
        spectrum_timeout_s=1,
    )


def test_config_path_is_independent_of_working_directory():
    assert DEFAULT_CONFIG_PATH.is_absolute()
    assert DEFAULT_CONFIG_PATH.name == "instruments.local.toml"
    assert DEFAULT_CONFIG_PATH.parent.name == "config"
    assert DEFAULT_CONFIG_PATH.is_file()
    assert load_config().schema_version == 2


def test_experiment_nests_instrument_lifecycles():
    events = []
    trace = run_experiment(
        FakeMmcsService(events),
        FakeSpectrumService(events),
        make_plan(),
    )
    assert trace == "trace"
    assert events == [
        "mmcs-connect",
        "spectrum-connect",
        "mmcs-start",
        "spectrum-start",
        "spectrum-result",
        "spectrum-stop",
        "mmcs-stop",
        "spectrum-disconnect",
        "mmcs-disconnect",
    ]


def test_spectrum_failure_still_stops_and_disconnects_everything():
    events = []
    with pytest.raises(AcquisitionError, match="injected acquisition"):
        run_experiment(
            FakeMmcsService(events),
            FakeSpectrumService(events, fail=True),
            make_plan(),
        )
    assert events[-4:] == [
        "spectrum-stop",
        "mmcs-stop",
        "spectrum-disconnect",
        "mmcs-disconnect",
    ]
