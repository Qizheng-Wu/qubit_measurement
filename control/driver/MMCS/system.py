"""Stateful public MMCS system and DAC channel API."""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Sequence

from .backend import MmcsBackend
from .errors import (
    ConnectionError,
    DeviceNotFoundError,
    HardwareCommandError,
    MmcsError,
    ValidationError,
)
from .models import (
    BoxConfig,
    DacAddress,
    DacLane,
    DacSequence,
    Inventory,
    PlayMode,
    TriggerCommand,
    TriggerProgram,
)

logger = logging.getLogger(__name__)


class SystemState(Enum):
    CREATED = auto()
    CONNECTED = auto()
    SAFE = auto()
    ARMED = auto()
    RUNNING = auto()
    FAULTED = auto()
    CLOSED = auto()


class DacChannel:
    """A discovered DAC I/Q pair owned by one :class:`MmcsSystem`."""

    __slots__ = ("_system", "address")

    def __init__(self, system: "MmcsSystem", address: DacAddress) -> None:
        self._system = system
        self.address = address

    def upload_iq(
        self,
        i,
        q,
        *,
        mode: PlayMode = PlayMode.ZERO_AFTER,
    ) -> None:
        self.upload_sequence(DacSequence.single(i, q, mode))

    def upload_sequence(self, sequence: DacSequence) -> None:
        self._system._upload_sequence(self.address, sequence)


class MmcsSystem:
    """Typed, safe lifecycle wrapper for one or more MMCS boxes."""

    def __init__(
        self,
        boxes: Sequence[BoxConfig],
        backend: MmcsBackend | None = None,
    ) -> None:
        box_values = tuple(boxes)
        if not box_values:
            raise ConnectionError("at least one MMCS box must be configured")
        if not all(isinstance(box, BoxConfig) for box in box_values):
            raise ConnectionError("boxes must contain only BoxConfig objects")
        names = [box.name for box in box_values]
        if len(names) != len(set(names)):
            raise ConnectionError("MMCS box names must be unique")
        if backend is None:
            from .vendor_backend import VendorBackend

            backend = VendorBackend()

        self.boxes = box_values
        self._box_names = frozenset(names)
        self._backend = backend
        self._inventory: Inventory | None = None
        self._channels: dict[DacAddress, DacChannel] = {}
        self._uploaded_segments: dict[DacAddress, int] = {}
        self._safe_master_box: str | None = None
        self._armed_master_box: str | None = None
        self.state = SystemState.CREATED

    def __enter__(self) -> "MmcsSystem":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except Exception:
                logger.exception("MMCS cleanup failed while another exception was active")
        return False

    @property
    def inventory(self) -> Inventory:
        if self._inventory is None:
            raise ConnectionError("MMCS system has not been connected")
        return self._inventory

    def connect(self) -> Inventory:
        self._require_state(SystemState.CREATED)
        try:
            inventory = self._backend.connect(self.boxes)
        except MmcsError:
            self.state = SystemState.FAULTED
            raise
        except Exception as exc:
            self.state = SystemState.FAULTED
            raise ConnectionError("MMCS backend connection failed") from exc
        self._inventory = inventory
        self.state = SystemState.CONNECTED
        return inventory

    def initialize_safe(self, *, master_box: str, timeout_s: float = 5.0) -> None:
        self._require_box(master_box)
        self._require_state(
            SystemState.CONNECTED,
            SystemState.SAFE,
            SystemState.ARMED,
            SystemState.FAULTED,
        )
        self._validate_timeout(timeout_s)
        try:
            self._backend.stop_all(master_box, timeout_s)
            self._backend.clear_trigger_memory()
        except MmcsError:
            self.state = SystemState.FAULTED
            raise
        except Exception as exc:
            self.state = SystemState.FAULTED
            raise HardwareCommandError("failed to put MMCS into a safe state") from exc
        self._uploaded_segments.clear()
        self._safe_master_box = master_box
        self._armed_master_box = None
        self.state = SystemState.SAFE

    def dac(self, address: DacAddress) -> DacChannel:
        if not isinstance(address, DacAddress):
            raise DeviceNotFoundError("DAC lookup requires a DacAddress")
        self._require_state(
            SystemState.CONNECTED,
            SystemState.SAFE,
            SystemState.ARMED,
            SystemState.RUNNING,
            SystemState.FAULTED,
        )
        if address not in self.inventory.dacs:
            raise DeviceNotFoundError(f"DAC was not discovered: {address}")
        if address not in self._channels:
            self._channels[address] = DacChannel(self, address)
        return self._channels[address]

    def arm(self, program: TriggerProgram) -> None:
        self._require_state(SystemState.SAFE)
        if not isinstance(program, TriggerProgram):
            raise ValidationError("arm requires a TriggerProgram")
        self._require_box(program.master_box)
        for address, events in program.channels.items():
            if address not in self.inventory.dacs:
                raise DeviceNotFoundError(f"trigger program references an undiscovered DAC: {address}")
            expected = self._uploaded_segments.get(address)
            if expected is None:
                raise ValidationError(f"no waveform has been uploaded to {address}")
            actual = sum(event.command == TriggerCommand.START for event in events)
            if actual != expected:
                raise ValidationError(
                    f"{address} has {expected} uploaded segment(s) but {actual} START event(s)"
                )

        try:
            self._backend.clear_trigger_memory()
            for address, events in program.channels.items():
                self._backend.set_dac_triggers(address, events)
            self._backend.set_level1(program.repetitions, program.period_ns)
        except Exception as exc:
            self._fault_after_error(program.master_box, exc, "failed to arm MMCS")
        self._armed_master_box = program.master_box
        self.state = SystemState.ARMED

    def run(self, *, master_box: str) -> None:
        self._require_state(SystemState.ARMED)
        self._require_box(master_box)
        if master_box != self._armed_master_box:
            raise ValidationError(
                f"program was armed for {self._armed_master_box!r}, not {master_box!r}"
            )
        try:
            self._backend.run(master_box)
        except Exception as exc:
            self._fault_after_error(master_box, exc, "failed to start MMCS")
        self.state = SystemState.RUNNING

    def wait(self, *, master_box: str, timeout_s: float) -> None:
        self._require_state(SystemState.RUNNING)
        self._require_box(master_box)
        if master_box != self._armed_master_box:
            raise ValidationError(
                f"program is running on {self._armed_master_box!r}, not {master_box!r}"
            )
        self._validate_timeout(timeout_s)
        try:
            self._backend.wait(master_box, timeout_s)
        except Exception as exc:
            self._fault_after_error(master_box, exc, "MMCS run did not finish cleanly")
        self.state = SystemState.ARMED

    def execute(self, program: TriggerProgram, *, timeout_s: float) -> None:
        self._validate_timeout(timeout_s)
        self.arm(program)
        self.run(master_box=program.master_box)
        self.wait(master_box=program.master_box, timeout_s=timeout_s)

    def close(self) -> None:
        if self.state is SystemState.CLOSED:
            return
        errors: list[BaseException] = []
        if self.state is not SystemState.CREATED:
            master_box = self._armed_master_box or self._safe_master_box or self.boxes[0].name
            try:
                self._backend.stop_all(master_box, 5.0)
            except Exception as exc:
                errors.append(exc)
            try:
                self._backend.clear_trigger_memory()
            except Exception as exc:
                errors.append(exc)
        try:
            self._backend.close()
        except Exception as exc:
            errors.append(exc)
        self._uploaded_segments.clear()
        self._armed_master_box = None
        self.state = SystemState.CLOSED
        if errors:
            raise HardwareCommandError("one or more MMCS cleanup operations failed") from errors[0]

    def _upload_sequence(self, address: DacAddress, sequence: DacSequence) -> None:
        self._require_state(SystemState.SAFE)
        if address not in self.inventory.dacs:
            raise DeviceNotFoundError(f"DAC was not discovered: {address}")
        if not isinstance(sequence, DacSequence):
            raise ValidationError("upload_sequence requires a DacSequence")
        try:
            if len(sequence.segments) == 1:
                segment = sequence.segments[0]
                self._backend.upload_single(address, DacLane.I, segment.i, sequence.mode)
                self._backend.upload_single(address, DacLane.Q, segment.q, sequence.mode)
            else:
                self._backend.upload_sequence(
                    address,
                    DacLane.I,
                    [segment.i for segment in sequence.segments],
                    sequence.mode,
                )
                self._backend.upload_sequence(
                    address,
                    DacLane.Q,
                    [segment.q for segment in sequence.segments],
                    sequence.mode,
                )
        except Exception as exc:
            self._fault_after_error(
                self._safe_master_box or self.boxes[0].name,
                exc,
                f"waveform upload failed for {address}",
            )
        self._uploaded_segments[address] = len(sequence.segments)

    def _fault_after_error(self, master_box: str, error: Exception, message: str) -> None:
        self.state = SystemState.FAULTED
        try:
            self._backend.stop_all(master_box, 5.0)
        except Exception:
            logger.exception("failed to stop MMCS while handling: %s", message)
        try:
            self._backend.clear_trigger_memory()
        except Exception:
            logger.exception("failed to clear MMCS trigger RAM while handling: %s", message)
        if isinstance(error, MmcsError):
            raise error
        raise HardwareCommandError(message) from error

    def _require_box(self, name: str) -> None:
        if name not in self._box_names:
            raise DeviceNotFoundError(f"MMCS box is not configured: {name!r}")

    def _require_state(self, *allowed: SystemState) -> None:
        if self.state not in allowed:
            names = ", ".join(state.name for state in allowed)
            raise HardwareCommandError(
                f"operation is invalid in state {self.state.name}; expected one of: {names}"
            )

    @staticmethod
    def _validate_timeout(timeout_s: float) -> None:
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise ValidationError("timeout_s must be a positive number")
