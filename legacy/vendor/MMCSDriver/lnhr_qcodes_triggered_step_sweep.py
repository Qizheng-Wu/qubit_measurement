import argparse
import socket
import sys
import time
from typing import Iterable

import numpy as np
from qcodes.instrument import Instrument
from qcodes.parameters import create_on_off_val_mapping
import qcodes.validators as vals


MULTILINE_QUERIES = {
    "?",
    "help?",
    "soft?",
    "hard?",
    "idn?",
    "health?",
    "ip?",
    "serial?",
    "contact?",
}

TRIGGER_MODE_TO_CODE = {
    "disable": 0,
    "start only": 1,
    "start stop": 2,
    "single step": 3,
}

AWG_TO_BOARD = {
    "a": "ab",
    "b": "ab",
    "c": "cd",
    "d": "cd",
}

AWG_CHANNEL_RANGES = {
    "a": range(1, 13),
    "b": range(1, 13),
    "c": range(13, 25),
    "d": range(13, 25),
}


class LnhrDacStepSweep(Instrument):
    """QCoDeS instrument wrapper for BASPI LNHR DAC II step-sweep setup."""

    def __init__(
        self,
        name: str,
        ip: str,
        port: int = 23,
        channel: int = 3,
        awg: str = "a",
        timeout: float = 5.0,
    ) -> None:
        super().__init__(name)
        self.ip = ip
        self.port = port
        self.channel = channel
        self.awg = awg.lower()
        self.timeout = timeout
        self._output_enabled_by_this_script = False
        self._awg_started_by_this_script = False
        self._awg_trigger_armed_by_this_script = False

        if self.awg not in AWG_TO_BOARD:
            raise ValueError("AWG must be one of: a, b, c, d")
        if self.channel not in AWG_CHANNEL_RANGES[self.awg]:
            allowed = AWG_CHANNEL_RANGES[self.awg]
            raise ValueError(
                f"AWG {self.awg.upper()} can only drive DAC channels "
                f"{allowed.start}..{allowed.stop - 1}"
            )

        self.add_parameter(
            "dc_voltage",
            unit="V",
            get_cmd=self.get_dc_voltage,
            set_cmd=self.set_dc_voltage,
            vals=vals.Numbers(-10.0, 10.0),
        )

        self.add_parameter(
            "output_enabled",
            get_cmd=self.get_output_enabled,
            set_cmd=self.set_output_enabled,
            val_mapping=create_on_off_val_mapping(on_val="ON", off_val="OFF"),
        )

        self.add_parameter(
            "awg_channel",
            get_cmd=self.get_awg_channel,
            set_cmd=self.set_awg_channel,
            vals=vals.Ints(1, 24),
        )

        self.add_parameter(
            "awg_cycles",
            get_cmd=self.get_awg_cycles,
            set_cmd=self.set_awg_cycles,
            vals=vals.Ints(0, 4_000_000_000),
        )

        self.add_parameter(
            "awg_trigger",
            get_cmd=self.get_awg_trigger,
            set_cmd=self.set_awg_trigger,
            vals=vals.Enum(*TRIGGER_MODE_TO_CODE.keys()),
        )

        self.add_parameter(
            "awg_running",
            get_cmd=self.get_awg_running,
            set_cmd=self.set_awg_running,
            val_mapping=create_on_off_val_mapping(on_val="START", off_val="STOP"),
        )

    @staticmethod
    def voltage_to_dac_value(voltage: float) -> int:
        return round((float(voltage) + 10.0) * 838860.74)

    @staticmethod
    def dac_value_to_voltage(dac_value: str) -> float:
        return round((int(dac_value.strip(), 16) / 838860.74) - 10.0, 6)

    def _exchange(self, command: str, expect_multiline: bool = False) -> str:
        command = command.strip()
        end_marker = b"\r\r" if expect_multiline else b"\r\n"

        with socket.create_connection((self.ip, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(command.encode("ascii") + b"\r\n")
            answer = sock.recv(4096)

            if expect_multiline:
                chunks = [answer]
                while end_marker not in b"".join(chunks):
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
                answer = b"".join(chunks)

        if not answer:
            raise TimeoutError(f"No answer from {self.ip}:{self.port} for {command!r}")

        return answer.decode("ascii", errors="replace").strip()

    def query(self, command: str) -> str:
        if "?" not in command:
            raise ValueError(f"Refusing to query a non-query command: {command!r}")
        command = command.strip().lower()
        return self._exchange(command, expect_multiline=command in MULTILINE_QUERIES)

    def write_command(self, command: str) -> None:
        if "?" in command:
            raise ValueError(f"Refusing to write a query command: {command!r}")
        answer = self._exchange(command)
        if answer != "0":
            raise RuntimeError(f"DAC rejected {command!r}: {answer!r}")

    def get_dc_voltage(self) -> float:
        return self.dac_value_to_voltage(self.query(f"{self.channel} v?"))

    def set_dc_voltage(self, voltage: float) -> None:
        self.write_command(f"{self.channel} {self.voltage_to_dac_value(voltage):x}")

    def set_channel_bandwidth(self, bandwidth: str) -> None:
        bandwidth = bandwidth.upper()
        if bandwidth not in {"HBW", "LBW"}:
            raise ValueError("Bandwidth must be HBW or LBW")
        self.write_command(f"{self.channel} {bandwidth}")

    def get_output_enabled(self) -> str:
        return self.query(f"{self.channel} s?")

    def set_output_enabled(self, enabled: str) -> None:
        self.write_command(f"{self.channel} {enabled}")
        if enabled == "ON":
            self._output_enabled_by_this_script = True

    def get_awg_channel(self) -> int:
        return int(self.query(f"c awg-{self.awg} ch?"))

    def set_awg_channel(self, channel: int) -> None:
        self.write_command(f"c awg-{self.awg} ch {channel}")

    def get_awg_cycles(self) -> int:
        return int(self.query(f"c awg-{self.awg} cs?"))

    def set_awg_cycles(self, cycles: int) -> None:
        self.write_command(f"c awg-{self.awg} cs {cycles}")

    def get_awg_trigger(self) -> str:
        code = int(self.query(f"c awg-{self.awg} tm?"))
        for name, value in TRIGGER_MODE_TO_CODE.items():
            if code == value:
                return name
        raise ValueError(f"Unknown trigger mode code from DAC: {code}")

    def set_awg_trigger(self, mode: str) -> None:
        self.write_command(f"c awg-{self.awg} tm {TRIGGER_MODE_TO_CODE[mode]}")
        if mode != "disable":
            self._awg_trigger_armed_by_this_script = True

    def get_awg_running(self) -> str:
        return "START" if int(self.query(f"c awg-{self.awg} s?")) else "STOP"

    def set_awg_running(self, state: str) -> None:
        self.write_command(f"c awg-{self.awg} {state}")
        if state == "START":
            self._awg_started_by_this_script = True

    def set_awg_clock_period_us(self, clock_period_us: int) -> None:
        board = AWG_TO_BOARD[self.awg]
        self.write_command(f"c awg-{board} cp {clock_period_us}")

    def clear_wave_memory(self) -> None:
        self.write_command(f"c wav-{self.awg} clr")

    def set_wave_memory_value(self, address: int, voltage: float) -> None:
        self.write_command(f"wav-{self.awg} {address:x} {voltage:.6f}")

    def write_wave_memory_to_awg(self) -> None:
        self.write_command(f"c wav-{self.awg} write")
        while int(self.query(f"c wav-{self.awg} busy?")):
            time.sleep(0.05)

    def set_awg_memory_size(self, size: int) -> None:
        self.write_command(f"c awg-{self.awg} ms {size}")

    def load_awg_waveform(self, voltages: Iterable[float]) -> None:
        waveform = list(float(v) for v in voltages)
        if not waveform:
            raise ValueError("Waveform cannot be empty")

        self.clear_wave_memory()
        for address, voltage in enumerate(waveform):
            self.set_wave_memory_value(address, voltage)

        self.write_wave_memory_to_awg()
        self.set_awg_memory_size(len(waveform))

        memory_size = int(self.query(f"c awg-{self.awg} ms?"))
        if memory_size != len(waveform):
            raise MemoryError(
                f"AWG memory size mismatch: set {len(waveform)} points, "
                f"device reports {memory_size}"
            )

    def communication_check(self) -> None:
        print("Communication check:")
        for command in (f"{self.channel} s?", f"{self.channel} v?"):
            print(f">>> {command}")
            print(self.query(command))
        print()

    def safe_stop(self, leave_output_on: bool) -> None:
        if leave_output_on:
            print("Leaving AWG/output state unchanged by request.")
            return

        try:
            if self._awg_trigger_armed_by_this_script:
                self.awg_trigger("disable")
            if self._awg_started_by_this_script:
                self.awg_running(False)
            if self._output_enabled_by_this_script:
                self.dc_voltage(0.0)
                self.output_enabled(False)
            print("Disabled AWG trigger if needed, set channel to 0 V, and disabled output.")
        except Exception as exc:
            print("WARNING: Could not confirm safe stop over the network.")
            print(f"Reason: {type(exc).__name__}: {exc}")
            print("Check the DAC front panel / Commander before relying on the output state.")


def build_step_values(start: float, stop: float, steps: int) -> np.ndarray:
    if steps < 2:
        raise ValueError("--steps must be at least 2")
    #values = np.linspace(start, stop, steps)
    values = np.array([0, 0.01, 0.03, 0.08, 0.4, 0.2])
    if np.any(values < -10.0) or np.any(values > 10.0):
        raise ValueError("All step voltages must stay within -10 V ... +10 V")
    return values


def run_software_sweep(dac: LnhrDacStepSweep, values: np.ndarray, dwell: float) -> None:
    print("Mode: software")
    print("The PC will step the DAC voltage directly. No external trigger is used.")
    print("Press Ctrl+C to stop.")
    print()

    dac.communication_check()
    dac.dc_voltage(float(values[0]))
    dac.output_enabled(True)

    while True:
        for value in values:
            dac.dc_voltage(float(value))
            print(f"{time.strftime('%H:%M:%S')}  {value:.6f} V")
            time.sleep(dwell)


def arm_external_trigger_sweep(
    dac: LnhrDacStepSweep,
    values: np.ndarray,
    cycles: int,
    clock_period_us: int,
) -> None:
    print("Mode: external-trigger")
    print("The DAC AWG is loaded with step values.")
    print("Trigger mode is set to 'single step': every external trigger edge advances one point.")
    print("Use trigger pulses at least 2 us wide; 10 us is a good first lab value.")
    print("Keep this script running while checking the oscilloscope.")
    print("Press Ctrl+C to stop and disable the output.")
    print()

    dac.communication_check()
    dac.output_enabled(False)
    dac.awg_running(False)
    dac.set_channel_bandwidth("HBW")
    dac.awg_channel(dac.channel)
    dac.awg_cycles(cycles)
    dac.set_awg_clock_period_us(clock_period_us)

    # Put the output at the first point before any external trigger arrives.
    # The AWG memory starts from the second point, so trigger #1 creates a
    # visible step instead of repeating the already-present start voltage.
    dac.dc_voltage(float(values[0]))
    trigger_values = values[1:]
    #trigger_values = list(values[1:]) + [values[0]]
    dac.load_awg_waveform(trigger_values)
    dac.awg_trigger("single step")
    dac.output_enabled(True)

    print("External-trigger step sweep is armed.")
    print(f"AWG {dac.awg.upper()} -> channel {dac.channel}")
    print(f"Initial value before triggers: {values[0]:.6f} V")
    print(f"Trigger-controlled values: {len(trigger_values)}")
    for index, value in enumerate(trigger_values, start=1):
        print(f"  trigger {index}: {value:.6f} V")
    print(f"Last value: {values[-1]:.6f} V")
    print(f"Cycles: {cycles} (0 means infinite repeat)")
    print("AWG is idle and waiting for external rising edges. Trigger #1 now changes the voltage.")
    print()

    while True:
        time.sleep(1.0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QCoDeS step-sweep preparation for BASPI LNHR DAC II."
    )
    parser.add_argument("--mode", choices=("software", "external-trigger"), default="software")
    parser.add_argument("--ip", default="192.168.0.5")
    parser.add_argument("--port", type=int, default=23)
    parser.add_argument("--channel", type=int, default=3)
    parser.add_argument("--awg", choices=("a", "b", "c", "d"), default="a")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--stop", type=float, default=0.5)
    parser.add_argument("--steps", type=int, default=11)
    parser.add_argument("--dwell", type=float, default=0.2, help="Software mode dwell time in seconds")
    parser.add_argument("--cycles", type=int, default=0, help="External-trigger AWG cycles; 0 means infinite")
    parser.add_argument(
        "--clock-period-us",
        type=int,
        default=1000,
        help="AWG clock period in microseconds. Mostly relevant for non-single-step modes.",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--leave-output-on",
        action="store_true",
        help="Do not stop/disable output when the script exits.",
    )
    args = parser.parse_args()

    values = build_step_values(args.start, args.stop, args.steps)
    dac = LnhrDacStepSweep(
        "lnhr_step_sweep",
        ip=args.ip,
        port=args.port,
        channel=args.channel,
        awg=args.awg,
        timeout=args.timeout,
    )

    print("LNHR DAC II QCoDeS step-sweep script")
    print(f"Target: {args.ip}:{args.port}")
    print(f"Channel: {args.channel}")
    print(f"Values: {args.start} V -> {args.stop} V, {args.steps} steps")
    print()

    try:
        if args.mode == "software":
            run_software_sweep(dac, values, args.dwell)
        else:
            arm_external_trigger_sweep(dac, values, args.cycles, args.clock_period_us)
    except KeyboardInterrupt:
        print()
        print("Stopping by user request...")
    finally:
        dac.safe_stop(args.leave_output_on)
        dac.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
