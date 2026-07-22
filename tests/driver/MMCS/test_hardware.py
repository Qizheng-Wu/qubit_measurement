from __future__ import annotations

import os

import numpy as np
import pytest

from control.driver.MMCS import (
    BoxConfig,
    DacAddress,
    DacPair,
    DacSequence,
    MmcsSystem,
    PlayMode,
    TriggerEvent,
    TriggerProgram,
    WaveSegment,
)


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        os.getenv("MMCS_HARDWARE") != "1" or os.getenv("MMCS_OPERATOR_CONFIRM") != "YES",
        reason="requires MMCS_HARDWARE=1 and MMCS_OPERATOR_CONFIRM=YES",
    ),
]


def test_scope_single_and_multi_segment_smoke() -> None:
    ip = os.getenv("MMCS_BOX1_IP", "192.168.4.8")
    slot = int(os.getenv("MMCS_DAC_SLOT", "3"))
    address = DacAddress("box1", slot, DacPair.CH12)

    sample_rate = 2_000_000_000
    samples = 80
    time_s = np.arange(samples) / sample_rate
    i_wave = 0.1 * np.sin(2 * np.pi * 100_000_000 * time_s)
    q_wave = 0.1 * np.cos(2 * np.pi * 100_000_000 * time_s)

    with MmcsSystem((BoxConfig("box1", ip),)) as mmcs:
        inventory = mmcs.connect()
        assert address in inventory.dacs
        mmcs.initialize_safe(master_box="box1")

        dac = mmcs.dac(address)
        dac.upload_iq(i_wave, q_wave, mode=PlayMode.ZERO_AFTER)
        mmcs.execute(
            TriggerProgram.single(
                dac=address,
                trigger_ns=40,
                period_ns=10_000,
                repetitions=5,
                master_box="box1",
            ),
            timeout_s=2,
        )

        mmcs.initialize_safe(master_box="box1")
        dac.upload_sequence(
            DacSequence(
                (
                    WaveSegment(np.full(80, 0.1), np.zeros(80)),
                    WaveSegment(np.full(80, -0.1), np.zeros(80)),
                ),
                mode=PlayMode.ZERO_AFTER,
            )
        )
        mmcs.execute(
            TriggerProgram(
                period_ns=10_000,
                repetitions=5,
                master_box="box1",
                channels={address: (TriggerEvent(40), TriggerEvent(240))},
            ),
            timeout_s=2,
        )
