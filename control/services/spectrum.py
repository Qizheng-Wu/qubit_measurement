"""Spectrum-analyzer connection and sweep lifecycle."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import numpy as np

from control.core.exceptions import AcquisitionError, InstrumentStateError, ValidationError
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver

from .base import BaseInstrumentService


class SpectrumAnalyzerRun:
    def __init__(self, service: "SpectrumAnalyzerService", config: SpectrumSweepConfig) -> None:
        self._service = service
        self._config = config
        self._result: SpectrumTrace | None = None

    @property
    def completed(self) -> bool:
        return self._result is not None

    def result(self, *, timeout_s: float) -> SpectrumTrace:
        if self._result is not None:
            return self._result
        self._service._require_active_run(self)
        self._result = self._service._finish(self._config, timeout_s=timeout_s)
        return self._result


class SpectrumAnalyzerService(BaseInstrumentService):
    def __init__(self, driver: SpectrumAnalyzerDriver) -> None:
        super().__init__(driver)
        self._hardware_running = False

    @property
    def driver(self) -> SpectrumAnalyzerDriver:
        return self._driver

    def _start(self, config: SpectrumSweepConfig) -> None:
        try:
            self.driver.set_start_hz(config.start_hz)
            self.driver.set_stop_hz(config.stop_hz)
            self.driver.set_points(config.points)
            self.driver.set_resolution_bandwidth_hz(config.resolution_bandwidth_hz)
            self.driver.set_input_attenuation_db(config.input_attenuation_db)
            self.driver.set_continuous(False)
            self.driver.trigger()
        except BaseException as exc:
            try:
                self.driver.abort()
            except Exception as cleanup_exc:
                exc.add_note(f"Spectrum analyzer abort also failed: {cleanup_exc}")
            try:
                self.driver.set_continuous(False)
            except Exception as cleanup_exc:
                exc.add_note(
                    f"Restoring spectrum-analyzer state also failed: {cleanup_exc}"
                )
            raise
        self._hardware_running = True

    def _finish(self, config: SpectrumSweepConfig, *, timeout_s: float) -> SpectrumTrace:
        if timeout_s <= 0:
            raise ValidationError("timeout_s must be positive")
        self.driver.wait_operation_complete(timeout_s)
        power = self.driver.fetch_trace_dbm(expected_points=config.points)
        self._hardware_running = False
        return SpectrumTrace(
            frequency_hz=np.linspace(config.start_hz, config.stop_hz, config.points),
            power_dbm=power,
            config=config,
            instrument=self.driver.identity,
            acquired_at=datetime.now(timezone.utc),
        )

    @contextmanager
    def running(self, config: SpectrumSweepConfig) -> Iterator[SpectrumAnalyzerRun]:
        self._require_connected()
        if self._active_run is not None:
            raise InstrumentStateError("Instrument service is already running")
        self._start(config)
        run = SpectrumAnalyzerRun(self, config)
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
                self.driver.set_continuous(False)
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
                else:
                    cleanup_error.add_note(f"Restoring continuous mode also failed: {exc}")
            self._hardware_running = False
            self._deactivate_run(run)
            if cleanup_error is not None:
                if primary_error is not None:
                    primary_error.add_note(
                        f"Spectrum-analyzer cleanup also failed: {cleanup_error}"
                    )
                else:
                    raise AcquisitionError(
                        "Spectrum-analyzer run failed to restore state"
                    ) from cleanup_error
