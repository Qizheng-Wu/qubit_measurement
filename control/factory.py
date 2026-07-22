"""Composition root that creates disconnected drivers from static config."""

from __future__ import annotations

from control.config.model import (
    ControlConfig,
    MmcsDeviceConfig,
    SpectrumAnalyzerDeviceConfig,
    VnaDeviceConfig,
)
from control.driver.mmcs import MmcsHardwareDriver
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver
from control.transport.mmcs_vendor import MmcsVendorTransport
from control.transport.visa import VisaTransport


class InstrumentFactory:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config

    @staticmethod
    def _visa_transport(config: VnaDeviceConfig | SpectrumAnalyzerDeviceConfig) -> VisaTransport:
        return VisaTransport(
            config.address,
            timeout_s=config.transport_timeout_s,
            read_termination=config.read_termination,
            write_termination=config.write_termination,
        )

    def create_vna(self, name: str) -> VnaDriver:
        config = self.config.require(name, VnaDeviceConfig)
        return VnaDriver(self._visa_transport(config))

    def create_spectrum_analyzer(self, name: str) -> SpectrumAnalyzerDriver:
        config = self.config.require(name, SpectrumAnalyzerDeviceConfig)
        return SpectrumAnalyzerDriver(self._visa_transport(config))

    def create_mmcs(self, name: str) -> MmcsHardwareDriver:
        config = self.config.require(name, MmcsDeviceConfig)
        return MmcsHardwareDriver(
            MmcsVendorTransport(config.boxes),
            shutdown_timeout_s=self.config.defaults.mmcs_execution.cleanup_timeout_s,
        )
