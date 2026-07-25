from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pytest
from pydantic import ValidationError

from control.core.exceptions import (
    AcquisitionError,
    ProtocolError,
    TransportTimeoutError,
)
from control.domain.sweep import SpectrumSweepConfig, VnaSweepConfig
from control.domain.power import ScalarPowerMeasurementConfig
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver
from control.services import SpectrumAnalyzerService, VnaService


class ScriptedVisaTransport:
    def __init__(self, *, query=None, binary=None, fail_writes=()):
        self.is_open = False
        self.commands = []
        self.query_responses = dict(query or {})
        self.binary_responses = dict(binary or {})
        self.fail_writes = set(fail_writes)
        self.timeout_s = 10.0

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, command):
        self.commands.append(("write", command))
        if command in self.fail_writes:
            raise RuntimeError(f"injected write failure: {command}")

    def query(self, command):
        self.commands.append(("query", command))
        response = self.query_responses[command]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, Exception):
            raise response
        return str(response)

    def query_float(self, command):
        return float(self.query(command))

    def query_int(self, command):
        return int(float(self.query(command)))

    def query_binary(self, command, **kwargs):
        self.commands.append(("binary", command, kwargs))
        return np.asarray(self.binary_responses[command])

    @contextmanager
    def temporary_timeout(self, timeout_s):
        previous = self.timeout_s
        self.timeout_s = timeout_s
        try:
            yield
        finally:
            self.timeout_s = previous


def test_vna_acquire_and_restore_output():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Keysight,E5071C,SN1,1.0", "OUTP?": "0", "*OPC?": "1"},
        binary={"CALC:DATA:SDAT?": [1, 2, 3, 4, 5, 6]},
    )
    service = VnaService(VnaDriver(transport))
    config = VnaSweepConfig(
        start_hz=1e9, stop_hz=2e9, points=3,
        bandwidth_hz=1e3, power_dbm=-30, averages=2,
    )

    with service.connected():
        with service.running(config) as run:
            trace = run.result(timeout_s=5)
            assert run.result(timeout_s=5) is trace
        assert transport.commands[-1] == ("write", "OUTP 0")

    np.testing.assert_allclose(trace.s_parameter, [1 + 2j, 3 + 4j, 5 + 6j])
    np.testing.assert_allclose(trace.frequency_hz, [1e9, 1.5e9, 2e9])
    assert trace.instrument.model == "E5071C"
    assert ("write", "OUTP 1") in transport.commands
    with pytest.raises(ValueError):
        trace.frequency_hz[0] = 0


def test_vna_protocol_error_aborts_and_restores():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Ceyear,3656D,SN2,1", "OUTP?": "ON", "*OPC?": "1"},
        binary={"CALC:DATA:SDAT?": [1, 2]},
    )
    service = VnaService(VnaDriver(transport))
    with service.connected():
        with pytest.raises(ProtocolError):
            with service.running(VnaSweepConfig(
                start_hz=1, stop_hz=2, points=2,
                bandwidth_hz=100, power_dbm=-20, averages=1,
            )) as run:
                run.result(timeout_s=1)
        assert ("write", ":ABORT") in transport.commands
        assert transport.commands[-1] == ("write", "OUTP 1")


def test_spectrum_analyzer_acquire():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Rohde&Schwarz,FPL1602,SN3,1", "*OPC?": "+1"},
        binary={"TRAC:DATA? TRACE1": [-80, -70, -75]},
    )
    service = SpectrumAnalyzerService(SpectrumAnalyzerDriver(transport))
    config = SpectrumSweepConfig(
        start_hz=4e9, stop_hz=5e9, points=3,
        resolution_bandwidth_hz=10e3, input_attenuation_db=10,
    )

    with service.connected():
        with service.running(config) as run:
            trace = run.result(timeout_s=3)
        assert transport.commands[-1] == ("write", ":INIT:CONT 0")

    np.testing.assert_array_equal(trace.power_dbm, [-80, -70, -75])
    assert ("write", ":INIT:IMM") in transport.commands


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VnaSweepConfig(start_hz=2, stop_hz=1, points=2, bandwidth_hz=100, power_dbm=-20, averages=1),
        lambda: VnaSweepConfig(start_hz=1, stop_hz=2, points=1, bandwidth_hz=100, power_dbm=-20, averages=1),
        lambda: VnaSweepConfig(start_hz=1, stop_hz=2, points=2, bandwidth_hz=100, power_dbm=20, averages=1),
        lambda: SpectrumSweepConfig(start_hz=1, stop_hz=2, points=2, resolution_bandwidth_hz=0, input_attenuation_db=0),
        lambda: SpectrumSweepConfig(start_hz=1, stop_hz=2, points=2, resolution_bandwidth_hz=100, input_attenuation_db=-1),
    ],
)
def test_invalid_sweep_config(factory):
    with pytest.raises(ValidationError):
        factory()


def test_operation_timeout_propagates_and_restores_transport_timeout():
    timeout = TransportTimeoutError("timeout")
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Vendor,Model,SN,FW", "OUTP?": "0", "*OPC?": timeout},
        binary={},
    )
    service = VnaService(VnaDriver(transport))
    with service.connected():
        with pytest.raises(TransportTimeoutError):
            with service.running(
                VnaSweepConfig(start_hz=1, stop_hz=2, points=2, bandwidth_hz=100, power_dbm=-20, averages=1)
            ) as run:
                run.result(timeout_s=2)
    assert transport.timeout_s == 10


def test_successful_vna_acquisition_reports_restore_failure():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Vendor,Model,SN,FW", "OUTP?": "0", "*OPC?": "1"},
        binary={"CALC:DATA:SDAT?": [1, 0, 2, 0]},
        fail_writes={"OUTP 0"},
    )
    service = VnaService(VnaDriver(transport))
    with service.connected():
        with pytest.raises(AcquisitionError, match="failed to restore state"):
            with service.running(
                VnaSweepConfig(start_hz=1, stop_hz=2, points=2, bandwidth_hz=100, power_dbm=-20, averages=1)
            ) as run:
                run.result(timeout_s=2)


def test_unconsumed_spectrum_run_aborts():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Vendor,Model,SN,FW"},
    )
    service = SpectrumAnalyzerService(SpectrumAnalyzerDriver(transport))
    config = SpectrumSweepConfig(
        start_hz=1, stop_hz=2, points=2,
        resolution_bandwidth_hz=1, input_attenuation_db=0,
    )
    with service.connected():
        with service.running(config):
            pass
        assert ("write", ":ABOR") in transport.commands


def test_scalar_marker_session_configures_once_and_uses_median():
    transport = ScriptedVisaTransport(
        query={
            "*IDN?": "Rohde&Schwarz,FPL1602,SN3,1",
            "*OPC?": ["1"] * 6,
            ":CALC:MARK1:Y?": [-80, -60, -70, -50, -40, -45],
        }
    )
    service = SpectrumAnalyzerService(SpectrumAnalyzerDriver(transport))
    config = ScalarPowerMeasurementConfig(
        frequency_hz=5e9,
        span_hz=2e6,
        points=201,
        resolution_bandwidth_hz=10e3,
        input_attenuation_db=20,
    )

    with service.connected():
        with service.scalar_power_session(config) as meter:
            first = meter.measure(repetitions=3, timeout_s=2)
            second = meter.measure(repetitions=3, timeout_s=2)

    assert first.readings_dbm == (-80.0, -60.0, -70.0)
    assert first.power_dbm == -70
    assert second.power_dbm == -45
    assert transport.commands.count(("write", "FREQ:CENT 5000000000 Hz")) == 1
    assert transport.commands.count(("write", ":INIT:IMM")) == 6
    assert ("write", ":CALC:MARK1:X 5000000000 Hz") in transport.commands
    assert transport.commands[-5:] == [
        ("write", ":ABOR"),
        ("write", ":INIT:CONT 0"),
        ("write", ":CALC:MARK1:STAT 0"),
        ("write", ":ABOR"),
        ("write", ":INIT:CONT 0"),
    ]


def test_scalar_marker_timeout_still_cleans_up():
    transport = ScriptedVisaTransport(
        query={
            "*IDN?": "Rohde&Schwarz,FPL1602,SN3,1",
            "*OPC?": TransportTimeoutError("timeout"),
        }
    )
    service = SpectrumAnalyzerService(SpectrumAnalyzerDriver(transport))
    config = ScalarPowerMeasurementConfig(
        frequency_hz=5e9,
        span_hz=2e6,
        points=201,
        resolution_bandwidth_hz=10e3,
        input_attenuation_db=20,
    )

    with service.connected():
        with pytest.raises(TransportTimeoutError):
            with service.scalar_power_session(config) as meter:
                meter.measure(timeout_s=1)
    assert ("write", ":ABOR") in transport.commands
    marker_off = transport.commands.index(("write", ":CALC:MARK1:STAT 0"))
    assert transport.commands[marker_off - 2:marker_off + 1] == [
        ("write", ":ABOR"),
        ("write", ":INIT:CONT 0"),
        ("write", ":CALC:MARK1:STAT 0"),
    ]


def test_marker_driver_rejects_nonfinite_power():
    transport = ScriptedVisaTransport(query={":CALC:MARK1:Y?": "nan"})
    driver = SpectrumAnalyzerDriver(transport)
    with pytest.raises(ProtocolError, match="non-finite"):
        driver.fetch_marker_power_dbm(1)
