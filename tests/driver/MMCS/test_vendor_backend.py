from __future__ import annotations

import struct

import numpy as np

from control.driver.MMCS import (
    BoxConfig,
    DacAddress,
    DacLane,
    DacPair,
    PlayMode,
    TriggerEvent,
    HardwareCommandError,
)
from control.driver.MMCS.vendor_backend import VendorBackend
from MMCSDriver.mmcs_driver.api.udp_base import udp_base


class FakeDriver:
    trigger_start = 1

    def __init__(self, box_ip_dict):
        self.box_ip_dict = box_ip_dict
        self.da = {
            "da_box1pcie3ch12": object(),
            "da_box2pcie11ch34": object(),
            "unexpected-device-name": object(),
        }
        self.bp = {}
        self.calls = []

    def sys_stop_all_borad(self, **kwargs):
        self.calls.append(("stop", kwargs))
        return 0

    def sys_clear_all_level2_trigger_ram(self):
        self.calls.append(("clear",))
        return 0

    def da_set_single_waveform(self, **kwargs):
        self.calls.append(("single", kwargs))
        return 0

    def da_set_multi_waveform(self, **kwargs):
        self.calls.append(("multi", kwargs))
        return 0

    def da_set_level2_trigger_ram(self, **kwargs):
        self.calls.append(("trigger", kwargs))
        return 0

    def sys_set_level1_trigger(self, **kwargs):
        self.calls.append(("level1", kwargs))
        return 0

    def sys_run_level1_trigger(self, **kwargs):
        self.calls.append(("run", kwargs))
        return 0

    def sys_wait_until_finish(self, **kwargs):
        self.calls.append(("wait", kwargs))
        return 0

    def sys_close(self):
        self.calls.append(("close",))
        return 0


def test_vendor_backend_maps_structured_addresses_and_playlist() -> None:
    created = []

    def factory(**kwargs):
        driver = FakeDriver(**kwargs)
        created.append(driver)
        return driver

    backend = VendorBackend(driver_factory=factory)
    boxes = (BoxConfig("box1", "192.168.4.8"), BoxConfig("box2", "192.168.4.9"))
    inventory = backend.connect(boxes)
    address = DacAddress("box1", 3, DacPair.CH12)
    assert address in inventory.dacs
    assert inventory.vendor_names[address] == "da_box1pcie3ch12"

    waves = (np.zeros(8), np.ones(8) * 0.1)
    backend.upload_sequence(address, DacLane.I, waves, PlayMode.HOLD_LAST)
    backend.set_dac_triggers(address, (TriggerEvent(40), TriggerEvent(80)))
    driver = created[0]
    multi = next(call[1] for call in driver.calls if call[0] == "multi")
    assert multi["name"] == "da_box1pcie3ch12"
    assert multi["playlist"] == [
        {"trigger": 1, "wave_idx": 0},
        {"trigger": 1, "wave_idx": 1},
    ]
    trigger = next(call[1] for call in driver.calls if call[0] == "trigger")
    assert trigger["time_stamp_list_ns"] == [40, 80]
    assert trigger["cmd_list"] == [1, 1]


def test_vendor_backend_treats_none_status_as_failure() -> None:
    class FailedDriver(FakeDriver):
        def da_set_single_waveform(self, **kwargs):
            return None

    backend = VendorBackend(driver_factory=lambda **kwargs: FailedDriver(**kwargs))
    backend.connect((BoxConfig("box1", "192.168.4.8"),))
    with np.testing.assert_raises(HardwareCommandError):
        backend.upload_single(
            DacAddress("box1", 3, DacPair.CH12),
            DacLane.I,
            np.zeros(8),
            PlayMode.ZERO_AFTER,
        )


class CaptureUdp:
    def __init__(self):
        self.payloads = []

    def send_b(self, data, ip, port):
        self.payloads.append((bytes(data), ip, port))


def test_vendor_packet_layout_is_unchanged() -> None:
    transport = CaptureUdp()
    protocol = udp_base(transport, ip="192.168.4.8", port=6002)
    protocol.send_package(3, [0x11223344, 0x55667788])
    payload, ip, port = transport.payloads[0]
    words = list(struct.unpack(f">{len(payload) // 4}I", payload))
    expected_without_checksum = [3, 1, 1, 2, 0x11223344, 0x55667788]
    assert words[:-1] == expected_without_checksum
    assert words[-1] == sum(expected_without_checksum) & 0xFFFFFFFF
    assert (ip, port) == ("192.168.4.8", 6002)
