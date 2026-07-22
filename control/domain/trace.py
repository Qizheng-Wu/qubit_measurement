"""Acquisition result value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from control.core.identity import InstrumentIdentity

if TYPE_CHECKING:
    from .sweep import SpectrumSweepConfig, VnaSweepConfig


def _immutable_copy(values: np.ndarray, *, dtype=None) -> np.ndarray:
    result = np.array(values, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


@dataclass(frozen=True, slots=True)
class VnaTrace:
    frequency_hz: np.ndarray
    s_parameter: np.ndarray
    config: "VnaSweepConfig"
    instrument: InstrumentIdentity
    acquired_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "frequency_hz", _immutable_copy(self.frequency_hz, dtype=float))
        object.__setattr__(self, "s_parameter", _immutable_copy(self.s_parameter, dtype=complex))


@dataclass(frozen=True, slots=True)
class SpectrumTrace:
    frequency_hz: np.ndarray
    power_dbm: np.ndarray
    config: "SpectrumSweepConfig"
    instrument: InstrumentIdentity
    acquired_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "frequency_hz", _immutable_copy(self.frequency_hz, dtype=float))
        object.__setattr__(self, "power_dbm", _immutable_copy(self.power_dbm, dtype=float))
