"""Industrial instrument-control package.

The package is intentionally independent from :mod:`lab4`.  Public APIs are
split into transport, driver, and domain layers.
"""

from .core.exceptions import ControlError
from .config import ControlConfig, load_control_config
from .domain import (
    SpectrumAnalyzerController,
    SpectrumSweepConfig,
    SpectrumTrace,
    VnaController,
    VnaSweepConfig,
    VnaTrace,
)
from .driver import MmcsHardwareDriver, SpectrumAnalyzerDriver, VnaDriver
from .factory import InstrumentFactory
from .transport import MmcsVendorTransport, VisaTransport

__all__ = [
    "ControlError",
    "ControlConfig",
    "InstrumentFactory",
    "MmcsHardwareDriver",
    "MmcsVendorTransport",
    "SpectrumAnalyzerController",
    "SpectrumAnalyzerDriver",
    "SpectrumSweepConfig",
    "SpectrumTrace",
    "VisaTransport",
    "VnaController",
    "VnaDriver",
    "VnaSweepConfig",
    "VnaTrace",
    "load_control_config",
]
