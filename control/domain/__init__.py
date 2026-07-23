"""High-level, strongly typed instrument workflows."""

from .sweep import (
    ResolvedSpectrumSweep,
    ResolvedVnaSweep,
    SpectrumSweepConfig,
    VnaSweepConfig,
)
from .trace import SpectrumTrace, VnaTrace
