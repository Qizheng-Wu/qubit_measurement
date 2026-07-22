"""Typed facade over the vendored MMCS API."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, Self

import numpy as np

from control.transport.mmcs_vendor import MmcsVendorTransport

logger = logging.getLogger(__name__)


class MmcsHardwareDriver:
    def __init__(self, transport: MmcsVendorTransport, *, shutdown_timeout_s: float) -> None:
        if shutdown_timeout_s <= 0:
            raise ValueError("shutdown_timeout_s must be positive")
        self.transport = transport
        self.shutdown_timeout_s = float(shutdown_timeout_s)
        self._active_master_box: str | None = None

    @property
    def is_connected(self) -> bool:
        return self.transport.is_open

    @property
    def generation(self) -> int:
        return self.transport.generation

    def connect(self) -> None:
        self.transport.open()

    def identify(self):
        """Return vendor FPGA version information when supported."""
        return self.transport.call("sys_get_fpga_version")

    def stop_all(self, master_box: str, *, timeout_s: float) -> None:
        self.transport.call("sys_stop_all_borad", master_box_name=master_box, timeout=timeout_s)
        if self._active_master_box == master_box:
            self._active_master_box = None

    def clear_all_trigger_ram(self) -> None:
        self.transport.call("sys_clear_all_level2_trigger_ram")

    def configure_level1_trigger(self, *, repetitions: int, period_ns: int) -> None:
        self.transport.call(
            "sys_set_level1_trigger", cycle_times=repetitions, cycle_period_ns=period_ns
        )

    def start(self, master_box: str) -> None:
        self.transport.call("sys_run_level1_trigger", master_box_name=master_box)
        self._active_master_box = master_box

    def wait(self, master_box: str, *, timeout_s: float) -> None:
        self.transport.call(
            "sys_wait_until_finish", master_box_name=master_box, timeout=timeout_s
        )

    def upload_dac_waveforms(
        self,
        *,
        board_id: str,
        channel: str,
        play_mode: str,
        waveforms: Sequence[np.ndarray],
        playlist: Sequence[dict[str, int]],
    ) -> None:
        self.transport.call(
            "da_set_multi_waveform",
            name=board_id,
            iq_channel_select=channel,
            play_mode=play_mode,
            waveform=[np.asarray(wave) for wave in waveforms],
            playlist=list(playlist),
        )

    def configure_dac_triggers(
        self, *, board_id: str, timestamps_ns: Sequence[int], commands: Sequence[int]
    ) -> None:
        self.transport.call(
            "da_set_level2_trigger_ram",
            name=board_id,
            time_stamp_list_ns=list(timestamps_ns),
            cmd_list=list(commands),
        )

    def clear_adc_data(self, board_id: str) -> None:
        self.transport.call("ad_clear_stored_data", name=board_id)

    def configure_adc_sampling(
        self, *, board_id: str, sample_length: int, repetitions: int
    ) -> None:
        self.transport.call(
            "ad_set_sample_parameter",
            name=board_id,
            sample_len=sample_length,
            cycle_times=repetitions,
        )

    def upload_demodulation_weights(
        self,
        *,
        board_id: str,
        channel: int,
        i_weights: np.ndarray,
        q_weights: np.ndarray,
    ) -> None:
        self.transport.call(
            "ad_set_demodulation_factor",
            name=board_id,
            freq_ch=channel,
            demo_i=np.asarray(i_weights),
            demo_q=np.asarray(q_weights),
        )

    def configure_adc_triggers(
        self, *, board_id: str, timestamps_ns: Sequence[int]
    ) -> None:
        timestamps = list(timestamps_ns)
        self.transport.call(
            "ad_set_level2_trigger_ram",
            name=board_id,
            time_stamp_list_ns=timestamps,
            cmd_list=[1] * len(timestamps),
        )

    def fetch_iq(self, board_id: str) -> tuple[Any, Any, Any, Any, Any]:
        return self.transport.call("ad_get_IQ", name=board_id)

    def safe_shutdown(self) -> None:
        if not self.is_connected:
            return
        if self._active_master_box is not None:
            self.stop_all(self._active_master_box, timeout_s=self.shutdown_timeout_s)
        self.clear_all_trigger_ram()

    def close(self) -> None:
        if not self.transport.is_open:
            return
        try:
            self.safe_shutdown()
        except Exception:
            logger.warning("MMCS safe shutdown failed", exc_info=True)
        finally:
            self.transport.close()

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self.close()
        except Exception as close_exc:
            if exc_value is not None:
                exc_value.add_note(f"Closing MMCS driver also failed: {close_exc}")
            else:
                raise
