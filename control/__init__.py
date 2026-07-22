"""Industrial instrument-control package.

The package is intentionally independent from :mod:`lab4`.  Public APIs are
split into transport, driver, and domain layers.
"""

from .core.exceptions import ControlError
from .domain import (
    SpectrumAnalyzerController,
    SpectrumSweepConfig,
    SpectrumTrace,
    VnaController,
    VnaSweepConfig,
    VnaTrace,
)
from .driver import MmcsHardwareDriver, SpectrumAnalyzerDriver, VnaDriver
from .transport import MmcsVendorTransport, VisaTransport

__all__ = [
    "ControlError",
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
]
