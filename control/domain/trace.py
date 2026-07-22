"""Acquisition result value objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

import numpy as np

from control.core.identity import InstrumentIdentity
from control.core.model import FrozenModel

if TYPE_CHECKING:
    from .sweep import SpectrumSweepConfig, VnaSweepConfig


def _immutable_copy(values: np.ndarray, *, dtype=None) -> np.ndarray:
    result = np.array(values, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


class VnaTrace(FrozenModel):
    frequency_hz: np.ndarray
    s_parameter: np.ndarray
    config: "VnaSweepConfig" if TYPE_CHECKING else Any
    instrument: InstrumentIdentity
    acquired_at: datetime

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "frequency_hz", _immutable_copy(self.frequency_hz, dtype=float))
        object.__setattr__(self, "s_parameter", _immutable_copy(self.s_parameter, dtype=complex))


class SpectrumTrace(FrozenModel):
    frequency_hz: np.ndarray
    power_dbm: np.ndarray
    config: "SpectrumSweepConfig" if TYPE_CHECKING else Any
    instrument: InstrumentIdentity
    acquired_at: datetime

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "frequency_hz", _immutable_copy(self.frequency_hz, dtype=float))
        object.__setattr__(self, "power_dbm", _immutable_copy(self.power_dbm, dtype=float))
