from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from control.core.exceptions import AcquisitionError, ValidationError
from control.core.identity import InstrumentIdentity
from control.domain.mmcs import DacChannel, DacPlayMode, TriggerCommand
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace
from experiments.mmcs_spectrum_demo import (
    acquire_while_mmcs_runs,
    analyze_spectrum,
    build_mmcs_output_program,
    generate_periodic_waveform,
    load_arbitrary_waveform,
    main,
    save_trace_csv,
)


def make_trace() -> SpectrumTrace:
    config = SpectrumSweepConfig(10e6, 30e6, 5, 100e3, 20)
    return SpectrumTrace(
        frequency_hz=np.linspace(10e6, 30e6, 5),
        power_dbm=np.array([-90, -80, -35, -82, -91]),
        config=config,
        instrument=InstrumentIdentity("R&S", "FPL", "1", "1", "R&S,FPL,1,1"),
        acquired_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize("kind", ["sine", "square"])
def test_generate_periodic_waveform(kind):
    waveform, actual_frequency = generate_periodic_waveform(
        kind, frequency_hz=20e6, amplitude=0.1, minimum_samples=800
    )
    assert waveform.ndim == 1
    assert waveform.size >= 800 and waveform.size % 8 == 0
    assert np.max(np.abs(waveform)) <= 0.1 + 1e-12
    assert actual_frequency == pytest.approx(20e6)


def test_load_arbitrary_waveform_normalizes_to_requested_amplitude(tmp_path):
    path = tmp_path / "wave.npy"
    np.save(path, np.arange(-4, 4, dtype=float))
    waveform = load_arbitrary_waveform(path, amplitude=0.25)
    assert waveform.size == 8
    assert np.max(np.abs(waveform)) == pytest.approx(0.25)


@pytest.mark.parametrize(
    "values",
    [np.zeros(8), np.zeros(7), np.array([0] * 7 + [np.nan]), np.zeros((2, 8))],
)
def test_invalid_arbitrary_waveform_is_rejected(tmp_path, values):
    path = tmp_path / "bad.npy"
    np.save(path, values)
    with pytest.raises(ValidationError):
        load_arbitrary_waveform(path, amplitude=0.1)


def test_build_mmcs_cycle_program():
    program = build_mmcs_output_program(
        np.zeros(8),
        board_id="da_box1pcie1ch12",
        channel=DacChannel.I,
        master_box="box1",
        run_duration_s=0.003,
        period_ns=1_000_000,
    )
    dac = program.dac_programs[0]
    assert program.repetitions == 3
    assert dac.play_mode is DacPlayMode.CYCLE
    assert [event.command for event in dac.triggers] == [
        TriggerCommand.START,
        TriggerCommand.STOP,
    ]


def test_analyze_and_save_spectrum(tmp_path):
    trace = make_trace()
    peak = analyze_spectrum(trace)
    assert peak.frequency_hz == 20e6
    assert peak.power_dbm == -35
    assert peak.prominence_db == pytest.approx(47)

    output = tmp_path / "nested" / "trace.csv"
    save_trace_csv(trace, output)
    saved = np.loadtxt(output, delimiter=",", skiprows=1)
    np.testing.assert_allclose(saved[:, 0], trace.frequency_hz)
    np.testing.assert_allclose(saved[:, 1], trace.power_dbm)


class FakeMmcsDriver:
    def __init__(self, stop_event):
        self.stop_event = stop_event
        self.stop_calls = 0

    def stop_all(self, master_box, *, timeout_s):
        self.stop_calls += 1
        self.stop_event.set()


class FakeExecutor:
    def __init__(self, started, stop_event):
        self.started = started
        self.stop_event = stop_event
        self.driver = FakeMmcsDriver(stop_event)

    def prepare(self, program):
        return program

    def run(self, prepared, *, timeout_s):
        self.started.set()
        time.sleep(0.01)
        self.stop_event.set()
        return object()


class FakeAnalyzer:
    def __init__(self, started, stop_event, *, fail=False):
        self.started = started
        self.stop_event = stop_event
        self.fail = fail

    def acquire(self, config, *, timeout_s):
        assert self.started.wait(1)
        if self.fail:
            raise AcquisitionError("injected analyzer failure")
        self.stop_event.set()
        return make_trace()


def test_concurrent_mmcs_output_and_spectrum_acquisition():
    started = threading.Event()
    stopped = threading.Event()
    executor = FakeExecutor(started, stopped)
    trace = acquire_while_mmcs_runs(
        executor,
        FakeAnalyzer(started, stopped),
        program=build_mmcs_output_program(
            np.zeros(8),
            board_id="da",
            channel=DacChannel.I,
            master_box="box1",
            run_duration_s=1,
        ),
        spectrum_config=make_trace().config,
        mmcs_timeout_s=2,
        spectrum_timeout_s=1,
        startup_delay_s=0,
    )
    assert trace.power_dbm[2] == -35
    assert executor.driver.stop_calls == 0


def test_analyzer_failure_stops_mmcs_output():
    started = threading.Event()
    stopped = threading.Event()
    executor = FakeExecutor(started, stopped)
    with pytest.raises(AcquisitionError, match="injected"):
        acquire_while_mmcs_runs(
            executor,
            FakeAnalyzer(started, stopped, fail=True),
            program=build_mmcs_output_program(
                np.zeros(8),
                board_id="da",
                channel=DacChannel.I,
                master_box="box1",
                run_duration_s=1,
            ),
            spectrum_config=make_trace().config,
            mmcs_timeout_s=2,
            spectrum_timeout_s=1,
            startup_delay_s=0,
        )
    # The worker finishes its current finite chunk; no unsafe concurrent STOP is sent.
    assert executor.driver.stop_calls == 0
    assert stopped.is_set()


def test_cli_defaults_to_dry_run(capsys):
    exit_code = main(
        [
            "--config",
            "config/instruments.example.toml",
            "--dac-board",
            "da_box1pcie1ch12",
        ]
    )
    assert exit_code == 0
    assert "Dry run only" in capsys.readouterr().out
