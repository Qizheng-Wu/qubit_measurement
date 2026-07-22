from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pytest

from control.core.exceptions import (
    AcquisitionError,
    ProtocolError,
    TransportTimeoutError,
    ValidationError,
)
from control.domain.sweep import (
    SpectrumAnalyzerController,
    SpectrumSweepConfig,
    VnaController,
    VnaSweepConfig,
)
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver


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
    driver = VnaDriver(transport)
    driver.connect()
    config = VnaSweepConfig(1e9, 2e9, 3, 1e3, -30, 2)

    trace = VnaController(driver).acquire(config, timeout_s=5)

    np.testing.assert_allclose(trace.s_parameter, [1 + 2j, 3 + 4j, 5 + 6j])
    np.testing.assert_allclose(trace.frequency_hz, [1e9, 1.5e9, 2e9])
    assert trace.instrument.model == "E5071C"
    assert ("write", "OUTP 1") in transport.commands
    assert transport.commands[-1] == ("write", "OUTP 0")
    with pytest.raises(ValueError):
        trace.frequency_hz[0] = 0


def test_vna_protocol_error_aborts_and_restores():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Ceyear,3656D,SN2,1", "OUTP?": "ON", "*OPC?": "1"},
        binary={"CALC:DATA:SDAT?": [1, 2]},
    )
    driver = VnaDriver(transport)
    driver.connect()
    with pytest.raises(ProtocolError):
        VnaController(driver).acquire(
            VnaSweepConfig(1, 2, 2, 100, -20, 1), timeout_s=1
        )
    assert ("write", ":ABORT") in transport.commands
    assert transport.commands[-1] == ("write", "OUTP 1")


def test_spectrum_analyzer_acquire():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Rohde&Schwarz,FPL1602,SN3,1", "*OPC?": "+1"},
        binary={"TRAC:DATA? TRACE1": [-80, -70, -75]},
    )
    driver = SpectrumAnalyzerDriver(transport)
    driver.connect()
    config = SpectrumSweepConfig(4e9, 5e9, 3, 10e3, 10)

    trace = SpectrumAnalyzerController(driver).acquire(config, timeout_s=3)

    np.testing.assert_array_equal(trace.power_dbm, [-80, -70, -75])
    assert ("write", ":INIT:IMM") in transport.commands
    assert transport.commands[-1] == ("write", ":INIT:CONT 0")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VnaSweepConfig(2, 1, 2, 100, -20, 1),
        lambda: VnaSweepConfig(1, 2, 1, 100, -20, 1),
        lambda: VnaSweepConfig(1, 2, 2, 100, 20, 1),
        lambda: SpectrumSweepConfig(1, 2, 2, 0, 0),
        lambda: SpectrumSweepConfig(1, 2, 2, 100, -1),
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
    driver = VnaDriver(transport)
    driver.connect()
    with pytest.raises(TransportTimeoutError):
        VnaController(driver).acquire(VnaSweepConfig(1, 2, 2, 100, -20, 1), timeout_s=2)
    assert transport.timeout_s == 10


def test_successful_vna_acquisition_reports_restore_failure():
    transport = ScriptedVisaTransport(
        query={"*IDN?": "Vendor,Model,SN,FW", "OUTP?": "0", "*OPC?": "1"},
        binary={"CALC:DATA:SDAT?": [1, 0, 2, 0]},
        fail_writes={"OUTP 0"},
    )
    driver = VnaDriver(transport)
    driver.connect()
    with pytest.raises(AcquisitionError, match="failed to restore state"):
        VnaController(driver).acquire(VnaSweepConfig(1, 2, 2, 100, -20, 1), timeout_s=2)
