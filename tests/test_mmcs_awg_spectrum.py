from __future__ import annotations

from datetime import datetime, timezone
from inspect import signature

import numpy as np
import pytest

from control.application import (
    AwgSpectrumEngineeringOverrides,
    MmcsAwgSpectrumExperiment,
    MmcsAwgSpectrumSpec,
)
from control.application.awg_spectrum import acquire_spectrum_while_mmcs_runs
from control.config import (
    ControlConfig, MmcsDacBoardConfig, MmcsDeviceConfig,
    SpectrumAnalyzerDeviceConfig, VisaConnectionConfig,
)
from control.core.exceptions import AcquisitionError, ConfigurationError
from control.core.identity import InstrumentIdentity
from control.domain.mmcs import DacChannel
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace


def make_config(sample_rate_hz=2e9):
    return ControlConfig(
        2,
        {
            "mmcs": MmcsDeviceConfig(
                {"box1": "192.0.2.1"},
                {"da": MmcsDacBoardConfig(sample_rate_hz)},
            ),
            "sa": SpectrumAnalyzerDeviceConfig(VisaConnectionConfig("TCPIP0::SA")),
        },
    )


def make_spec(**changes):
    values = dict(
        mmcs_name="mmcs",
        spectrum_analyzer_name="sa",
        master_box="box1",
        dac_board_id="da",
        dac_channel=DacChannel.I,
        tone_frequency_hz=20e6,
        tone_amplitude=0.02,
        tone_phase_rad=0.0,
        spectrum_span_hz=10e6,
    )
    values.update(changes)
    return MmcsAwgSpectrumSpec(**values)


def make_trace():
    config = SpectrumSweepConfig(10e6, 30e6, 5, 100e3, 20)
    return SpectrumTrace(
        np.linspace(10e6, 30e6, 5),
        np.array([-90, -80, -35, -82, -91]),
        config,
        InstrumentIdentity("R&S", "FPL", "1", "1", "R&S,FPL,1,1"),
        datetime.now(timezone.utc),
    )


def test_spec_has_no_sample_rate_and_all_fields_are_required():
    assert "dac_sample_rate_hz" not in signature(MmcsAwgSpectrumSpec).parameters
    with pytest.raises(TypeError):
        MmcsAwgSpectrumSpec()


def test_resolve_uses_board_sample_rate_and_shared_defaults():
    resolved = MmcsAwgSpectrumExperiment(make_config(2.4e9)).resolve(make_spec())
    assert resolved.tone.spec.sample_rate_hz == 2.4e9
    assert resolved.tone.spec.minimum_samples == 800
    assert resolved.spectrum_config.points == 501
    assert resolved.spectrum_config.resolution_bandwidth_hz == 100e3
    assert resolved.spectrum_config.input_attenuation_db == 20
    assert resolved.output_safety_window_s == 35
    assert resolved.program.period_ns == 1_000_000


def test_engineering_overrides_cannot_change_sample_rate():
    assert "sample_rate_hz" not in signature(AwgSpectrumEngineeringOverrides).parameters
    overrides = AwgSpectrumEngineeringOverrides(
        points=101,
        resolution_bandwidth_hz=20e3,
        input_attenuation_db=30,
        acquisition_timeout_s=8,
        minimum_waveform_samples=1600,
        period_ns=2_000_000,
        start_trigger_ns=80,
        safety_margin_s=2,
    )
    resolved = MmcsAwgSpectrumExperiment(make_config(2.4e9)).resolve(make_spec(), overrides)
    assert resolved.tone.spec.sample_rate_hz == 2.4e9
    assert resolved.tone.spec.minimum_samples == 1600
    assert resolved.spectrum_config.points == 101
    assert resolved.spectrum_config.resolution_bandwidth_hz == 20e3
    assert resolved.output_safety_window_s == 10


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"dac_board_id": "missing"}, "DAC board"),
        ({"master_box": "missing"}, "master box"),
        ({"spectrum_analyzer_name": "mmcs"}, "expected SpectrumAnalyzerDeviceConfig"),
    ],
)
def test_resolve_rejects_unknown_or_wrong_hardware_before_connect(changes, message):
    with pytest.raises(ConfigurationError, match=message):
        MmcsAwgSpectrumExperiment(make_config()).resolve(make_spec(**changes))


class FakeExecutor:
    def __init__(self, events, fail_stop=False):
        self.events, self.fail_stop = events, fail_stop
    def prepare(self, program): self.events.append("prepare"); return program
    def start(self, prepared): self.events.append("start"); return prepared
    def stop(self, running):
        self.events.append("stop")
        if self.fail_stop: raise RuntimeError("injected stop failure")


class FakeAnalyzer:
    def __init__(self, events, fail=False): self.events, self.fail = events, fail
    def acquire(self, config, *, timeout_s):
        self.events.append("acquire")
        if self.fail: raise AcquisitionError("injected acquisition failure")
        return make_trace()


def test_acquisition_occurs_between_start_and_stop():
    events = []
    resolved = MmcsAwgSpectrumExperiment(make_config()).resolve(make_spec())
    trace = acquire_spectrum_while_mmcs_runs(
        FakeExecutor(events), FakeAnalyzer(events), program=resolved.program,
        spectrum_config=resolved.spectrum_config, spectrum_timeout_s=1,
    )
    assert events == ["prepare", "start", "acquire", "stop"]
    assert trace.power_dbm[2] == -35


def test_acquisition_failure_still_stops_and_remains_primary():
    events = []
    resolved = MmcsAwgSpectrumExperiment(make_config()).resolve(make_spec())
    with pytest.raises(AcquisitionError, match="injected acquisition") as caught:
        acquire_spectrum_while_mmcs_runs(
            FakeExecutor(events, fail_stop=True), FakeAnalyzer(events, fail=True),
            program=resolved.program, spectrum_config=resolved.spectrum_config,
            spectrum_timeout_s=1,
        )
    assert events == ["prepare", "start", "acquire", "stop"]
    assert any("Stopping MMCS" in note for note in caught.value.__notes__)
