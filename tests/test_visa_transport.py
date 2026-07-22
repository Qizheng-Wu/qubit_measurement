from __future__ import annotations

import numpy as np
import pytest
import pyvisa

from control.core.exceptions import ProtocolError, TransportTimeoutError
from control.transport.visa import VisaTransport


class FakeResource:
    def __init__(self):
        self.timeout = 0
        self.closed = False
        self.writes = []

    def write(self, command):
        self.writes.append(command)

    def query(self, command):
        if command == "TIMEOUT":
            raise pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
        return {"FLOAT?": "1.25\n", "INT?": "3.0\n"}[command]

    def query_binary_values(self, command, **kwargs):
        return kwargs["container"]([1.0, 2.0])

    def close(self):
        self.closed = True


class FakeResourceManager:
    def __init__(self, resource):
        self.resource = resource
        self.closed = False
        self.open_kwargs = None

    def open_resource(self, name, **kwargs):
        self.open_kwargs = (name, kwargs)
        return self.resource

    def close(self):
        self.closed = True


def test_visa_transport_lifecycle_and_queries():
    resource = FakeResource()
    manager = FakeResourceManager(resource)
    transport = VisaTransport(
        "TCPIP::example",
        timeout_s=2.5,
        resource_manager_factory=lambda: manager,
    )

    assert not transport.is_open
    transport.open()
    transport.open()
    assert resource.timeout == 2500
    assert transport.query_float("FLOAT?") == 1.25
    assert transport.query_int("INT?") == 3
    np.testing.assert_array_equal(
        transport.query_binary("TRACE?", datatype="f", is_big_endian=False),
        [1.0, 2.0],
    )

    with transport.temporary_timeout(7):
        assert resource.timeout == 7000
    assert resource.timeout == 2500

    transport.close()
    transport.close()
    assert resource.closed and manager.closed


def test_visa_timeout_is_translated():
    resource = FakeResource()
    transport = VisaTransport(
        "TCPIP::example",
        resource_manager_factory=lambda: FakeResourceManager(resource),
    )
    transport.open()
    with pytest.raises(TransportTimeoutError):
        transport.query("TIMEOUT")


def test_numeric_protocol_error():
    resource = FakeResource()
    resource.query = lambda command: "not-a-number"
    transport = VisaTransport(
        "TCPIP::example",
        resource_manager_factory=lambda: FakeResourceManager(resource),
    )
    transport.open()
    with pytest.raises(ProtocolError):
        transport.query_float("BAD?")
