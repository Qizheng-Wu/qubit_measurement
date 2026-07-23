"""VNA connection and sweep lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import numpy as np

from control.core.exceptions import AcquisitionError, InstrumentStateError, ValidationError
from control.domain.sweep import VnaSweepConfig
from control.domain.trace import VnaTrace
from control.driver.vna import VnaDriver, VnaSweepMode

from .base import BaseInstrumentService


class VnaRun:
    def __init__(self, service: "VnaService", config: VnaSweepConfig) -> None:
        self._service = service
        self._config = config
        self._result: VnaTrace | None = None

    @property
    def completed(self) -> bool:
        return self._result is not None

    def result(self, *, timeout_s: float) -> VnaTrace:
        if self._result is not None:
            return self._result
        self._service._require_active_run(self)
        self._result = self._service._finish(self._config, timeout_s=timeout_s)
        return self._result


class VnaService(BaseInstrumentService):
    def __init__(self, driver: VnaDriver) -> None:
        super().__init__(driver)
        self._hardware_running = False

    @property
    def driver(self) -> VnaDriver:
        return self._driver

    def _start(self, config: VnaSweepConfig) -> bool:
        original_output = self.driver.get_output()
        try:
            self.driver.set_start_hz(config.start_hz)
            self.driver.set_stop_hz(config.stop_hz)
            self.driver.set_points(config.points)
            self.driver.set_bandwidth_hz(config.bandwidth_hz)
            self.driver.set_power_dbm(config.power_dbm)
            self.driver.set_averages(config.averages)
            self.driver.set_output(True)
            self.driver.clear_averages()
            self.driver.arm_bus_trigger()
            self.driver.trigger()
        except BaseException as exc:
            try:
                self.driver.abort()
            except Exception as cleanup_exc:
                exc.add_note(f"VNA abort also failed: {cleanup_exc}")
            try:
                self.driver.set_sweep_mode(VnaSweepMode.HOLD)
                self.driver.set_output(original_output)
            except Exception as cleanup_exc:
                exc.add_note(f"Restoring VNA state also failed: {cleanup_exc}")
            raise
        self._hardware_running = True
        return original_output

    def _finish(self, config: VnaSweepConfig, *, timeout_s: float) -> VnaTrace:
        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        self.driver.wait_operation_complete(timeout_s)
        data = self.driver.fetch_complex_trace(expected_points=config.points)
        self._hardware_running = False
        return VnaTrace(
            frequency_hz=np.linspace(config.start_hz, config.stop_hz, config.points),
            s_parameter=data,
            config=config,
            instrument=self.driver.identity,
            acquired_at=datetime.now(timezone.utc),
        )

    @contextmanager
    def running(self, config: VnaSweepConfig) -> Iterator[VnaRun]:
        self._require_connected()
        if self._active_run is not None:
            raise InstrumentStateError("Instrument service is already running")
        original_output = self._start(config)
        run = VnaRun(self, config)
        self._activate_run(run)
        primary_error: BaseException | None = None
        try:
            yield run
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: Exception | None = None
            if self._hardware_running:
                try:
                    self.driver.abort()
                except Exception as exc:
                    cleanup_error = exc
            try:
                self.driver.set_sweep_mode(VnaSweepMode.HOLD)
                self.driver.set_output(original_output)
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
                else:
                    cleanup_error.add_note(f"Restoring VNA state also failed: {exc}")
            self._hardware_running = False
            self._deactivate_run(run)
            if cleanup_error is not None:
                if primary_error is not None:
                    primary_error.add_note(f"Restoring VNA state also failed: {cleanup_error}")
                else:
                    raise AcquisitionError("VNA run failed to restore state") from cleanup_error
