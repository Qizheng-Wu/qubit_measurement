"""Backend boundary between the public MMCS API and a transport implementation."""

from __future__ import annotations

from typing import Protocol, Sequence

from numpy.typing import NDArray

from .models import (
    BoxConfig,
    DacAddress,
    DacLane,
    Inventory,
    PlayMode,
    TriggerEvent,
)


class MmcsBackend(Protocol):
    def connect(self, boxes: Sequence[BoxConfig]) -> Inventory: ...

    def close(self) -> None: ...

    def stop_all(self, master_box: str, timeout_s: float) -> None: ...

    def clear_trigger_memory(self) -> None: ...

    def upload_single(
        self,
        address: DacAddress,
        lane: DacLane,
        wave: NDArray,
        mode: PlayMode,
    ) -> None: ...

    def upload_sequence(
        self,
        address: DacAddress,
        lane: DacLane,
        waves: Sequence[NDArray],
        mode: PlayMode,
    ) -> None: ...

    def set_dac_triggers(
        self,
        address: DacAddress,
        events: Sequence[TriggerEvent],
    ) -> None: ...

    def set_level1(self, repetitions: int, period_ns: int) -> None: ...

    def run(self, master_box: str) -> None: ...

    def wait(self, master_box: str, timeout_s: float) -> None: ...
