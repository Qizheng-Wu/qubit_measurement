from __future__ import annotations

from collections.abc import Sequence

from control.driver.MMCS import BoxConfig, DacAddress, Inventory


class FakeBackend:
    def __init__(self, dacs: Sequence[DacAddress]) -> None:
        self.dacs = tuple(dacs)
        self.calls: list[tuple] = []
        self.fail_on: str | None = None

    def _record(self, name, *values):
        self.calls.append((name, *values))
        if self.fail_on == name:
            raise RuntimeError(f"injected {name} failure")

    def connect(self, boxes: Sequence[BoxConfig]) -> Inventory:
        self._record("connect", tuple(boxes))
        return Inventory(boxes, self.dacs)

    def close(self) -> None:
        self._record("close")

    def stop_all(self, master_box: str, timeout_s: float) -> None:
        self._record("stop_all", master_box, timeout_s)

    def clear_trigger_memory(self) -> None:
        self._record("clear_trigger_memory")

    def upload_single(self, address, lane, wave, mode) -> None:
        self._record("upload_single", address, lane, wave.copy(), mode)

    def upload_sequence(self, address, lane, waves, mode) -> None:
        self._record(
            "upload_sequence",
            address,
            lane,
            tuple(wave.copy() for wave in waves),
            mode,
        )

    def set_dac_triggers(self, address, events) -> None:
        self._record("set_dac_triggers", address, tuple(events))

    def set_level1(self, repetitions: int, period_ns: int) -> None:
        self._record("set_level1", repetitions, period_ns)

    def run(self, master_box: str) -> None:
        self._record("run", master_box)

    def wait(self, master_box: str, timeout_s: float) -> None:
        self._record("wait", master_box, timeout_s)
