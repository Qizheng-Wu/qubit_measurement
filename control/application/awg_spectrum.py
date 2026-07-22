"""Coordinate MMCS output with one spectrum-analyzer acquisition."""

from control.domain.mmcs import MmcsProgram
from control.domain.sweep import SpectrumSweepConfig
from control.domain.trace import SpectrumTrace

from .mmcs import MmcsExecutor
from .sweeps import SpectrumAnalyzerController


def acquire_spectrum_while_mmcs_runs(
    executor: MmcsExecutor,
    analyzer: SpectrumAnalyzerController,
    *,
    program: MmcsProgram,
    spectrum_config: SpectrumSweepConfig,
    spectrum_timeout_s: float,
) -> SpectrumTrace:
    executor.prepare(program)
    executor.start()
    try:
        return analyzer.acquire(spectrum_config, timeout_s=spectrum_timeout_s)
    finally:
        executor.stop()
