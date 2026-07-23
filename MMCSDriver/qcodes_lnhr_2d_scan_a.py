"""
QCoDeS-style LNHR DAC II 2D scan test.

This script reproduces the Commander setup you tested:
    x-axis: RMP-A / STEP A on DAC CH1, -1 V -> +1 V, 11 levels
    y-axis: AWG-A ramp on DAC CH11, -1 V -> +1 V, about 100 ms per line

Expected oscilloscope view:
    LNHR CH1  -> slow staircase x-axis
    LNHR CH11 -> repeated fast y-axis ramp

Run examples:
    python qcodes_lnhr_2d_scan_a.py arm
    python qcodes_lnhr_2d_scan_a.py start
    python qcodes_lnhr_2d_scan_a.py run
    python qcodes_lnhr_2d_scan_a.py status
    python qcodes_lnhr_2d_scan_a.py stop
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Sequence

try:
    from qcodes.instrument import Instrument
    from qcodes.validators import Enum, Ints, Numbers
except ImportError as exc:
    raise ImportError(
        "QCoDeS is not installed in this Python environment. Install it with: "
        "python -m pip install qcodes"
    ) from exc


OLD_CODE_DIR = Path(r"C:\Users\admin\Documents\Codex\2026-05-18\files-mentioned-by-the-user-docx")
if str(OLD_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(OLD_CODE_DIR))

from telnet import LNHRDAC  # noqa: E402


def linear_points(start: float, stop: float, count: int) -> list[float]:
    if count < 2:
        raise ValueError("count must be at least 2")
    step = (stop - start) / (count - 1)
    return [start + i * step for i in range(count)]


class LNHRDacII2D(Instrument):
    """Small QCoDeS wrapper for LNHR DAC II 2D-Scan A."""

    def __init__(self, name: str, host: str = "192.168.0.5", port: int = 23, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.host = host
        self.port = port
        self._dac = LNHRDAC(host, port, name=name)

        self.add_parameter(
            "x_channel",
            label="RMP-A x-axis DAC channel",
            vals=Ints(1, 12),
            get_cmd=lambda: int(self.ask_lnhr("C RMP-A CH?")),
            set_cmd=lambda value: self.write_lnhr(f"C RMP-A CH {int(value)}"),
        )
        self.add_parameter(
            "y_channel",
            label="AWG-A y-axis DAC channel",
            vals=Ints(1, 12),
            get_cmd=lambda: int(self.ask_lnhr("C AWG-A CH?")),
            set_cmd=lambda value: self.write_lnhr(f"C AWG-A CH {int(value)}"),
        )
        self.add_parameter(
            "x_start",
            label="x start voltage",
            unit="V",
            vals=Numbers(-10, 10),
            get_cmd=lambda: float(self.ask_lnhr("C RMP-A STAV?")),
            set_cmd=lambda value: self.write_lnhr(f"C RMP-A STAV {float(value):.9g}"),
        )
        self.add_parameter(
            "x_stop",
            label="x stop voltage",
            unit="V",
            vals=Numbers(-10, 10),
            get_cmd=lambda: float(self.ask_lnhr("C RMP-A STOV?")),
            set_cmd=lambda value: self.write_lnhr(f"C RMP-A STOV {float(value):.9g}"),
        )
        self.add_parameter(
            "awg_a_trigger_mode",
            label="AWG-A external trigger mode",
            vals=Ints(0, 3),
            get_cmd=lambda: int(self.ask_lnhr("C AWG-A TM?")),
            set_cmd=lambda value: self.write_lnhr(f"C AWG-A TM {int(value)}"),
        )
        self.add_parameter(
            "normal_or_adaptive",
            label="2D scan mode",
            vals=Enum("normal", "adaptive"),
            get_cmd=lambda: "adaptive" if self.ask_lnhr("C AWG-A RLD?") == "1" else "normal",
            set_cmd=self.set_2d_mode,
        )

    def write_lnhr(self, command: str, hold_connection: bool = False) -> None:
        print(f"> {command}", flush=True)
        self._dac.send_command(command, hold_connection=hold_connection)

    def ask_lnhr(self, command: str, hold_connection: bool = False) -> str:
        print(f"> {command}", flush=True)
        reply = self._dac.send_query(command, hold_connection=hold_connection).strip()
        print(f"< {reply}", flush=True)
        return reply

    def set_2d_mode(self, mode: str) -> None:
        if mode == "normal":
            self.write_lnhr("C AWG-A RLD 0")
            self.write_lnhr("C AWG-A AP 0")
            self.write_lnhr("C AWG-A SHIV 0")
        elif mode == "adaptive":
            self.write_lnhr("C AWG-A RLD 1")
            self.write_lnhr("C AWG-A AP 1")
        else:
            raise ValueError("mode must be normal or adaptive")

    def configure_scan_a(
        self,
        x_channel: int = 1,
        y_channel: int = 11,
        x_start: float = -1.0,
        x_stop: float = 1.0,
        x_levels: int = 11,
        y_start: float = -1.0,
        y_stop: float = 1.0,
        y_points: int = 1001,
        y_ramp_time_s: float = 0.100,
        mode: str = "normal",
    ) -> None:
        """Configure 2D-Scan A but do not start it yet."""

        if not (1 <= x_channel <= 12 and 1 <= y_channel <= 12):
            raise ValueError("This Scan A test uses the lower board; channels must be 1..12")
        if x_channel == y_channel:
            raise ValueError("x_channel and y_channel must be different")
        if x_levels < 10:
            raise ValueError("LNHR STEP 2D scan needs at least 10 x levels")
        if y_points < 2:
            raise ValueError("y_points must be at least 2")
        if y_ramp_time_s < 0.006:
            raise ValueError("Auto-start AWG needs y_ramp_time_s >= 6 ms")
        if any(abs(v) > 10 for v in (x_start, x_stop, y_start, y_stop)):
            raise ValueError("LNHR output voltages must stay within +/-10 V")

        y_clock_period_us = y_ramp_time_s * 1_000_000 / y_points
        if y_clock_period_us < 10:
            raise ValueError("AWG clock period would be below the LNHR 10 us minimum")

        x_ramp_time_s = max(0.050, x_levels * 0.005)
        y_wave = linear_points(y_start, y_stop, y_points)

        print()
        print("Configuring LNHR 2D-Scan A:", flush=True)
        print(f"  x: CH{x_channel}, {x_start:+.6f} V -> {x_stop:+.6f} V, {x_levels} levels", flush=True)
        print(f"  y: CH{y_channel}, {y_start:+.6f} V -> {y_stop:+.6f} V, {y_points} AWG points", flush=True)
        print(f"  y line time: {y_ramp_time_s:.6f} s, AWG clock period: {y_clock_period_us:.3f} us", flush=True)
        print(f"  mode: {mode}", flush=True)
        print()

        for command in [
            "C AWG-A TM 0",
            "C AWG-A STOP",
            "C RMP-A STOP",
            f"{x_channel} OFF",
            f"{y_channel} OFF",
            f"{x_channel} HBW",
            f"{y_channel} HBW",
            "C AWG-AB ONLY 0",
            f"C RMP-A CH {x_channel}",
            f"C RMP-A STAV {x_start:.9g}",
            f"C RMP-A STOV {x_stop:.9g}",
            f"C RMP-A RT {x_ramp_time_s:.9g}",
            "C RMP-A RS 0",
            "C RMP-A CS 1",
            "C RMP-A STEP 1",
            f"C AWG-A CH {y_channel}",
            "C AWG-A CS 1",
            "C AWG-A AS 1",
            f"C AWG-AB CP {y_clock_period_us:.9g}",
            "C WAV-A CLR",
        ]:
            self.write_lnhr(command, hold_connection=True)

        print("Writing y-axis ramp into WAV-A ...", flush=True)
        for index, voltage in enumerate(y_wave):
            self.write_lnhr(f"WAV-A {index:04X} {voltage:.9g}", hold_connection=True)

        self._dac._disconnect_from_DAC(hold_connection=False)

        self.write_lnhr("C WAV-A WRITE")
        self._wait_until_not_busy("C WAV-A BUSY?")

        self.write_lnhr(f"C AWG-A MS {y_points}", hold_connection=True)
        self.set_2d_mode(mode)
        self.write_lnhr(f"{x_channel} ON", hold_connection=True)
        self.write_lnhr(f"{y_channel} ON")

        print()
        print("ARMED.", flush=True)
        print("Use the 'start' action to run one 2D scan.", flush=True)

    def start_scan_a(self) -> None:
        """Start RMP-A and then start AWG-A once; Auto-Start continues the scan."""
        self.write_lnhr("C AWG-A TM 0")
        self.write_lnhr("C AWG-A STOP")
        self.write_lnhr("C RMP-A STOP")
        self.write_lnhr("C RMP-A START")
        time.sleep(0.1)
        self.write_lnhr("C AWG-A START")
        print("2D scan started.", flush=True)

    def stop_scan_a(self) -> None:
        self.write_lnhr("C AWG-A TM 0")
        self.write_lnhr("C AWG-A STOP")
        self.write_lnhr("C RMP-A STOP")
        print("2D scan stopped.", flush=True)

    def show_status(self, x_channel: int = 1, y_channel: int = 11) -> None:
        commands = [
            "IDN?",
            "C RMP-A STEP?",
            "C RMP-A S?",
            "C RMP-A CD?",
            "C RMP-A SD?",
            "C RMP-A SSV?",
            "C RMP-A ST?",
            "C RMP-A CH?",
            "C RMP-A STAV?",
            "C RMP-A STOV?",
            "C RMP-A RT?",
            "C RMP-A RS?",
            "C RMP-A CS?",
            "C AWG-A S?",
            "C AWG-A CD?",
            "C AWG-A CH?",
            "C AWG-A MS?",
            "C AWG-A CS?",
            "C AWG-A AS?",
            "C AWG-A RLD?",
            "C AWG-A AP?",
            "C AWG-A SHIV?",
            "C AWG-A TM?",
            "C AWG-AB CP?",
            f"{x_channel} S?",
            f"{x_channel} BW?",
            f"{y_channel} S?",
            f"{y_channel} BW?",
        ]
        for command in commands:
            self.ask_lnhr(command)

    def _wait_until_not_busy(self, query: str, timeout_s: float = 30.0) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.ask_lnhr(query) == "0":
                return
            time.sleep(0.2)
        raise TimeoutError(f"Timed out waiting for {query} to become 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QCoDeS LNHR 2D-Scan A test")
    parser.add_argument("action", choices=["arm", "start", "run", "status", "stop"], nargs="?", default="run")
    parser.add_argument("--host", default="192.168.0.5")
    parser.add_argument("--port", type=int, default=23)
    parser.add_argument("--name", default="lnhr_2d")
    parser.add_argument("--x-channel", type=int, default=1)
    parser.add_argument("--y-channel", type=int, default=11)
    parser.add_argument("--x-start", type=float, default=-1.0)
    parser.add_argument("--x-stop", type=float, default=1.0)
    parser.add_argument("--x-levels", type=int, default=11)
    parser.add_argument("--y-start", type=float, default=-1.0)
    parser.add_argument("--y-stop", type=float, default=1.0)
    parser.add_argument("--y-points", type=int, default=1001)
    parser.add_argument("--y-ramp-time-s", type=float, default=0.100)
    parser.add_argument("--mode", choices=["normal", "adaptive"], default="normal")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lnhr = LNHRDacII2D(args.name, host=args.host, port=args.port)
    try:
        if args.action in ("arm", "run"):
            lnhr.configure_scan_a(
                x_channel=args.x_channel,
                y_channel=args.y_channel,
                x_start=args.x_start,
                x_stop=args.x_stop,
                x_levels=args.x_levels,
                y_start=args.y_start,
                y_stop=args.y_stop,
                y_points=args.y_points,
                y_ramp_time_s=args.y_ramp_time_s,
                mode=args.mode,
            )
        if args.action in ("start", "run"):
            lnhr.start_scan_a()
        elif args.action == "status":
            lnhr.show_status(args.x_channel, args.y_channel)
        elif args.action == "stop":
            lnhr.stop_scan_a()
    finally:
        lnhr.close()


if __name__ == "__main__":
    main()
