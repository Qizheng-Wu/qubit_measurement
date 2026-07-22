"""Immutable MMCS acquisition results."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from control.core.model import FrozenModel


def _readonly(values) -> np.ndarray:
    result = np.array(values, copy=True)
    result.setflags(write=False)
    return result


class MmcsIqResult(FrozenModel):
    i_sum: np.ndarray
    q_sum: np.ndarray
    i_average: np.ndarray
    q_average: np.ndarray
    state_flags: np.ndarray

    def model_post_init(self, __context: Any) -> None:
        for name in ("i_sum", "q_sum", "i_average", "q_average", "state_flags"):
            object.__setattr__(self, name, _readonly(getattr(self, name)))


class MmcsResult(FrozenModel):
    iq_by_adc: Mapping[str, MmcsIqResult]
    period_ns: int
    repetitions: int
    elapsed_s: float
    program_fingerprint: str

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "iq_by_adc", MappingProxyType(dict(self.iq_by_adc)))
