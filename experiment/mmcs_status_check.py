"""Perform a minimal MMCS communication and status check."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from control.factory import InstrumentFactory
from control.services import MmcsService
from experiment.config import load_config


def check_mmcs_status(mmcs: MmcsService) -> Any:
    """Connect to MMCS, send one FPGA-status query, and return its response."""

    with mmcs.connected():
        return mmcs.check_status()


def main() -> int:
    mmcs_name = 'mmcs'

    config = load_config()
    mmcs = InstrumentFactory(config).create_mmcs_service(mmcs_name)

    print(f"Sending MMCS status query to {mmcs_name!r}...")
    response = check_mmcs_status(mmcs)
    print(f"MMCS status response: {response!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
