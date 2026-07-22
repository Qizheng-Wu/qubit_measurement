"""Immutable MMCS acquisition results."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import numpy as np


def _readonly(values) -> np.ndarray:
    result = np.array(values, copy=True)
    result.setflags(write=False)
    return result


@dataclass(frozen=True, slots=True)
class MmcsIqResult:
    i_sum: np.ndarray
    q_sum: np.ndarray
    i_average: np.ndarray
    q_average: np.ndarray
    state_flags: np.ndarray

    def __post_init__(self) -> None:
        for name in ("i_sum", "q_sum", "i_average", "q_average", "state_flags"):
            object.__setattr__(self, name, _readonly(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class MmcsResult:
    iq_by_adc: Mapping[str, MmcsIqResult]
    period_ns: int
    repetitions: int
    elapsed_s: float
    program_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "iq_by_adc", MappingProxyType(dict(self.iq_by_adc)))
