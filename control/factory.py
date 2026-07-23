"""Composition root that creates disconnected instrument services."""

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
from control.services import MmcsService, SpectrumAnalyzerService, VnaService
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

    def _create_vna_driver(self, name: str) -> VnaDriver:
        config = self.config.require(name, VnaDeviceConfig)
        return VnaDriver(self._visa_transport(config))

    def _create_spectrum_analyzer_driver(self, name: str) -> SpectrumAnalyzerDriver:
        config = self.config.require(name, SpectrumAnalyzerDeviceConfig)
        return SpectrumAnalyzerDriver(self._visa_transport(config))

    def _create_mmcs_driver(self, name: str) -> MmcsHardwareDriver:
        config = self.config.require(name, MmcsDeviceConfig)
        return MmcsHardwareDriver(
            MmcsVendorTransport(config.boxes),
            shutdown_timeout_s=self.config.defaults.mmcs_execution.cleanup_timeout_s,
        )

    def create_vna_service(self, name: str) -> VnaService:
        return VnaService(self._create_vna_driver(name))

    def create_spectrum_analyzer_service(self, name: str) -> SpectrumAnalyzerService:
        return SpectrumAnalyzerService(self._create_spectrum_analyzer_driver(name))

    def create_mmcs_service(self, name: str) -> MmcsService:
        return MmcsService(
            self._create_mmcs_driver(name),
            cleanup_timeout_s=self.config.defaults.mmcs_execution.cleanup_timeout_s,
        )
