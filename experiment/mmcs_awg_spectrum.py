"""Shared execution helper for a simultaneous MMCS and spectrum acquisition."""

from __future__ import annotations

from typing import Any


def run_experiment(mmcs: Any, spectrum: Any, plan: Any) -> Any:
    """Run both instruments with deterministic nested cleanup."""

    with mmcs.connected(), spectrum.connected():
        with mmcs.running(plan.mmcs_program):
            with spectrum.running(plan.spectrum_config) as spectrum_run:
                return spectrum_run.result(timeout_s=plan.spectrum_timeout_s)
