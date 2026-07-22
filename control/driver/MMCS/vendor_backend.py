"""Adapter for the bundled vendor MMCS SDK."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from numpy.typing import NDArray

from .errors import (
    ConnectionError,
    DeviceNotFoundError,
    HardwareCommandError,
    MmcsError,
    TimeoutError,
    ValidationError,
)
from .models import (
    BoxConfig,
    DacAddress,
    DacLane,
    DacPair,
    Inventory,
    PlayMode,
    TriggerEvent,
)

logger = logging.getLogger(__name__)


class VendorBackend:
    """Translate the typed v1 API into calls to the legacy vendor driver."""

    def __init__(self, driver_factory: Callable[..., Any] | None = None) -> None:
        self._driver_factory = driver_factory
        self._driver: Any | None = None
        self._inventory: Inventory | None = None
        self._names: dict[DacAddress, str] = {}

    def connect(self, boxes: Sequence[BoxConfig]) -> Inventory:
        if self._driver is not None:
            raise ConnectionError("vendor backend is already connected")
        unsupported = [box for box in boxes if box.port != 6002]
        if unsupported:
            raise ValidationError("the bundled vendor SDK only supports remote UDP port 6002")
        try:
            factory = self._driver_factory
            if factory is None:
                from MMCSDriver.mmcs_driver import MmcsDriver

                factory = MmcsDriver
            driver = factory(box_ip_dict={box.name: box.ip for box in boxes})
            names = self._discover_dacs(driver, boxes)
        except MmcsError:
            raise
        except Exception as exc:
            raise ConnectionError("failed to connect to and discover MMCS boxes") from exc

        self._driver = driver
        self._names = names
        self._inventory = Inventory(boxes, names, names)
        return self._inventory

    @staticmethod
    def _discover_dacs(driver: Any, boxes: Sequence[BoxConfig]) -> dict[DacAddress, str]:
        result: dict[DacAddress, str] = {}
        box_names = sorted((box.name for box in boxes), key=len, reverse=True)
        for vendor_name in driver.da:
            address: DacAddress | None = None
            for box_name in box_names:
                prefix = f"da_{box_name}pcie"
                if not vendor_name.startswith(prefix):
                    continue
                suffix = vendor_name[len(prefix) :]
                if "ch" not in suffix:
                    continue
                slot_raw, pair_raw = suffix.rsplit("ch", 1)
                try:
                    address = DacAddress(box_name, int(slot_raw), DacPair(pair_raw))
                except (ValueError, ValidationError):
                    address = None
                break
            if address is None:
                logger.warning("ignoring unrecognized vendor DAC name %s", vendor_name)
                continue
            if address in result:
                raise ConnectionError(f"duplicate DAC address discovered: {address}")
            result[address] = vendor_name
        return result

    def close(self) -> None:
        if self._driver is None:
            return
        driver, self._driver = self._driver, None
        self._inventory = None
        self._names = {}
        try:
            close = getattr(driver, "sys_close", None)
            if close is not None:
                self._require_success(close(), "close vendor MMCS transport")
                return
            seen: set[int] = set()
            for backplane in getattr(driver, "bp", {}).values():
                udp = backplane.sdk.udev.udp
                if id(udp) not in seen:
                    seen.add(id(udp))
                    udp.close()
        except Exception as exc:
            raise HardwareCommandError("failed to close the vendor MMCS transport") from exc

    def stop_all(self, master_box: str, timeout_s: float) -> None:
        driver = self._require_driver()
        self._call(
            "stop all boards",
            driver.sys_stop_all_borad,
            master_box_name=master_box,
            timeout=timeout_s,
        )

    def clear_trigger_memory(self) -> None:
        driver = self._require_driver()
        self._call("clear trigger memory", driver.sys_clear_all_level2_trigger_ram)

    def upload_single(
        self,
        address: DacAddress,
        lane: DacLane,
        wave: NDArray,
        mode: PlayMode,
    ) -> None:
        driver = self._require_driver()
        self._call(
            f"upload {lane.name} waveform to {address}",
            driver.da_set_single_waveform,
            name=self._vendor_name(address),
            iq_channel_select=lane.value,
            wave=wave,
            play_mode=mode.value,
        )

    def upload_sequence(
        self,
        address: DacAddress,
        lane: DacLane,
        waves: Sequence[NDArray],
        mode: PlayMode,
    ) -> None:
        driver = self._require_driver()
        playlist = [
            {"trigger": driver.trigger_start, "wave_idx": index}
            for index in range(len(waves))
        ]
        self._call(
            f"upload {lane.name} sequence to {address}",
            driver.da_set_multi_waveform,
            name=self._vendor_name(address),
            iq_channel_select=lane.value,
            play_mode=mode.value,
            waveform=list(waves),
            playlist=playlist,
        )

    def set_dac_triggers(
        self,
        address: DacAddress,
        events: Sequence[TriggerEvent],
    ) -> None:
        driver = self._require_driver()
        self._call(
            f"configure triggers for {address}",
            driver.da_set_level2_trigger_ram,
            name=self._vendor_name(address),
            time_stamp_list_ns=[event.at_ns for event in events],
            cmd_list=[int(event.command) for event in events],
        )

    def set_level1(self, repetitions: int, period_ns: int) -> None:
        driver = self._require_driver()
        self._call(
            "configure level-1 trigger",
            driver.sys_set_level1_trigger,
            cycle_times=repetitions,
            cycle_period_ns=period_ns,
        )

    def run(self, master_box: str) -> None:
        driver = self._require_driver()
        self._call(
            "start level-1 trigger",
            driver.sys_run_level1_trigger,
            master_box_name=master_box,
        )

    def wait(self, master_box: str, timeout_s: float) -> None:
        driver = self._require_driver()
        try:
            result = driver.sys_wait_until_finish(
                master_box_name=master_box,
                timeout=timeout_s,
            )
        except TimeoutError:
            raise
        except Exception as exc:
            if exc.__class__.__name__ in {"TimeoutError", "MmcsVendorTimeoutError"}:
                raise TimeoutError(f"MMCS run exceeded {timeout_s:g} s") from exc
            raise HardwareCommandError("wait for MMCS run failed") from exc
        self._require_success(result, "wait for MMCS run")

    def _vendor_name(self, address: DacAddress) -> str:
        try:
            return self._names[address]
        except KeyError as exc:
            raise DeviceNotFoundError(f"DAC was not discovered: {address}") from exc

    def _require_driver(self) -> Any:
        if self._driver is None:
            raise ConnectionError("vendor backend is not connected")
        return self._driver

    def _call(self, operation: str, function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        try:
            result = function(*args, **kwargs)
        except MmcsError:
            raise
        except Exception as exc:
            if exc.__class__.__name__ in {"TimeoutError", "MmcsVendorTimeoutError"}:
                raise TimeoutError(f"{operation} timed out") from exc
            raise HardwareCommandError(f"{operation} failed") from exc
        self._require_success(result, operation)
        return result

    @staticmethod
    def _require_success(result: Any, operation: str) -> None:
        if result != 0:
            raise HardwareCommandError(f"{operation} returned failure status {result!r}")
