from __future__ import annotations

import pytest

from control.core.exceptions import InstrumentStateError
from control.services.base import BaseInstrumentService


class FakeDriver:
    def __init__(self, *, fail_connect=False, fail_close=False):
        self.is_connected = False
        self.fail_connect = fail_connect
        self.fail_close = fail_close
        self.events = []

    def __enter__(self):
        self.events.append("connect")
        if self.fail_connect:
            raise RuntimeError("injected connect failure")
        self.is_connected = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events.append("close")
        self.is_connected = False
        if self.fail_close:
            close_error = RuntimeError("injected close failure")
            if exc_value is not None:
                exc_value.add_note(str(close_error))
            else:
                raise close_error


class DummyService(BaseInstrumentService):
    pass


def test_connected_opens_and_closes_driver():
    driver = FakeDriver()
    service = DummyService(driver)
    with service.connected():
        assert service.is_connected
        with pytest.raises(InstrumentStateError, match="already connected"):
            with service.connected():
                pass
    assert not service.is_connected
    assert driver.events == ["connect", "close"]


def test_connect_failure_does_not_enter_body():
    driver = FakeDriver(fail_connect=True)
    service = DummyService(driver)
    entered = False
    with pytest.raises(RuntimeError, match="connect failure"):
        with service.connected():
            entered = True
    assert not entered
    assert not service.is_connected


def test_body_error_survives_close_failure():
    service = DummyService(FakeDriver(fail_close=True))
    with pytest.raises(ValueError, match="primary") as captured:
        with service.connected():
            raise ValueError("primary")
    assert any("close failure" in note for note in captured.value.__notes__)


def test_close_failure_is_reported_after_successful_body():
    service = DummyService(FakeDriver(fail_close=True))
    with pytest.raises(RuntimeError, match="close failure"):
        with service.connected():
            pass
