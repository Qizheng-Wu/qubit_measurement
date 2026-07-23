"""
Generate front-panel MMCS DAC/AWG trigger pulses for an external comparator.

Use this as the trigger source in this chain:

    MMCS front-panel DAC/AWG SMA
        -> comparator input
        -> comparator TTL output
        -> LNHR DAC II Trig In AWG-A

The Basel/LNHR side should be armed separately with the QCoDeS script in the
QCoDeS project. This script only creates the MMCS front-panel pulse train.
"""

from __future__ import annotations

import argparse
import math

import numpy as np
from mmcs_driver import MmcsDriver


POINTS_PER_US = 2000  # MMCS examples use 2000 DAC points for 1 us.


def round_up_to_multiple(value: int, multiple: int) -> int:
    return int(math.ceil(value / multiple) * multiple)


def build_pulse(amplitude: float, width_us: float, tail_us: float) -> np.ndarray:
    if amplitude == 0 or amplitude < -1 or amplitude > 1:
        raise ValueError("--amplitude is normalized and must be in [-1, 1], excluding 0.")
    if width_us <= 0:
        raise ValueError("--width-us must be positive.")
    if tail_us < 0:
        raise ValueError("--tail-us must be zero or positive.")

    high_points = round_up_to_multiple(round(width_us * POINTS_PER_US), 8)
    tail_points = round_up_to_multiple(round(tail_us * POINTS_PER_US), 8)
    if tail_points == 0:
        tail_points = 8

    return np.concatenate(
        [
            np.full(high_points, amplitude, dtype=float),
            np.zeros(tail_points, dtype=float),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MMCS front-panel DAC/AWG pulse generator for scope/comparator trigger tests."
    )
    parser.add_argument("--box-ip", default="192.168.4.8", help="MMCS box IP address")
    parser.add_argument("--master-box", default="box1", help="MMCS master box name")
    parser.add_argument(
        "--dac-name",
        default="da_box1pcie5ch12",
        help=(
            "MMCS DAC group name. For the photographed front panel: "
            "slot 05 awg1 -> da_box1pcie5ch12 --iq i; "
            "slot 05 awg2 -> da_box1pcie5ch12 --iq q; "
            "slot 05 awg3 -> da_box1pcie5ch34 --iq i; "
            "slot 05 awg4 -> da_box1pcie5ch34 --iq q."
        ),
    )
    parser.add_argument(
        "--iq",
        choices=("i", "q"),
        default="i",
        help="i/q selects the physical channel in the DAC group; default is slot 05 awg1.",
    )
    parser.add_argument("--list-channels", action="store_true", help="print detected DAC channels and exit")
    parser.add_argument(
        "--amplitude",
        type=float,
        default=-0.8,
        help=(
            "normalized MMCS DAC amplitude, -1..1. On the photographed setup, "
            "negative normalized amplitude produces a positive oscilloscope pulse."
        ),
    )
    parser.add_argument("--width-us", type=float, default=10.0, help="pulse high width in microseconds")
    parser.add_argument("--tail-us", type=float, default=2.0, help="zero tail after the high pulse")
    parser.add_argument("--period-us", type=float, default=1000.0, help="time between pulses in microseconds")
    parser.add_argument("--count", type=int, default=20, help="number of pulses to output")
    parser.add_argument("--reset-system", action="store_true", help="reset all MMCS boards before configuring the pulse")
    parser.add_argument("--leave-armed", action="store_true", help="do not send stop/clear commands at the end")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise ValueError("--count must be at least 1.")

    pulse = build_pulse(args.amplitude, args.width_us, args.tail_us)
    pulse_len_us = len(pulse) / POINTS_PER_US
    if args.period_us <= pulse_len_us:
        raise ValueError(
            f"--period-us must be longer than the pulse waveform length, "
            f"currently {pulse_len_us:.3f} us."
        )

    driver = MmcsDriver(box_ip_dict={args.master_box: args.box_ip})
    print("Detected MMCS DAC groups:")
    for name in driver.da.keys():
        print(f"  {name}")

    if args.list_channels:
        return 0

    dac_name = args.dac_name or next(iter(driver.da.keys()))
    if dac_name not in driver.da:
        raise ValueError(f"Unknown --dac-name {dac_name!r}. Run with --list-channels first.")

    print()
    print("MMCS front AWG trigger pulse")
    print(f"Box: {args.master_box} at {args.box_ip}")
    print(f"DAC group: {dac_name}, IQ channel: {args.iq}")
    print(f"Pulse: normalized {args.amplitude}, width {args.width_us} us")
    print(f"Period: {args.period_us} us, count: {args.count}")
    print("Connect this SMA output either to the oscilloscope or to the comparator input.")
    print()

    if args.reset_system:
        driver.sys_reset_whole_system()

    driver.sys_clear_all_level2_trigger_ram()
    driver.sys_stop_all_borad(master_box_name=args.master_box)

    driver.da_set_single_waveform(
        name=dac_name,
        iq_channel_select=args.iq,
        wave=pulse,
        play_mode="end_with_zero",
    )
    driver.da_set_level2_trigger_ram(
        name=dac_name,
        time_stamp_list_ns=[20],
        cmd_list=[driver.trigger_start],
    )

    cycle_period_ns = round_up_to_multiple(round(args.period_us * 1000), 4)
    driver.sys_set_level1_trigger(
        cycle_times=args.count,
        cycle_period_ns=cycle_period_ns,
    )
    driver.sys_run_level1_trigger(master_box_name=args.master_box)
    driver.sys_wait_until_finish(master_box_name=args.master_box)

    if not args.leave_armed:
        driver.sys_clear_all_level2_trigger_ram()
        driver.sys_stop_all_borad(master_box_name=args.master_box)

    print("Done. The MMCS pulse train has finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
