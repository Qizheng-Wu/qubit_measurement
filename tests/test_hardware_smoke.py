"""Explicitly enabled laboratory hardware smoke tests."""

from __future__ import annotations

import os

import numpy as np
import pytest

from control.domain.mmcs import (
    AdcProgram,
    DacChannel,
    DacPlayMode,
    DacProgram,
    DacWaveform,
    DemodulationWeights,
    MmcsExecutor,
    MmcsProgram,
    PlaylistEntry,
    TriggerEvent,
)
from control.domain.sweep import (
    SpectrumAnalyzerController,
    SpectrumSweepConfig,
    VnaController,
    VnaSweepConfig,
)
from control.driver.mmcs import MmcsHardwareDriver
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver
from control.transport.mmcs_vendor import MmcsVendorTransport
from control.transport.visa import VisaTransport


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        os.getenv("RUN_HARDWARE_TESTS") != "1",
        reason="set RUN_HARDWARE_TESTS=1 to enable laboratory hardware tests",
    ),
]


def test_vna_low_power_short_sweep():
    resource = os.environ.get("LAB_VNA_RESOURCE")
    if not resource:
        pytest.skip("LAB_VNA_RESOURCE is not configured")
    with VnaDriver(VisaTransport(resource)) as driver:
        trace = VnaController(driver).acquire(
            VnaSweepConfig(4e9, 4.01e9, 11, 1e5, -60), timeout_s=30
        )
    assert trace.s_parameter.shape == (11,)


def test_spectrum_analyzer_short_sweep():
    resource = os.environ.get("LAB_SA_RESOURCE")
    if not resource:
        pytest.skip("LAB_SA_RESOURCE is not configured")
    with SpectrumAnalyzerDriver(VisaTransport(resource)) as driver:
        trace = SpectrumAnalyzerController(driver).acquire(
            SpectrumSweepConfig(4e9, 4.01e9, 11, 1e5, 20), timeout_s=30
        )
    assert trace.power_dbm.shape == (11,)


def test_mmcs_zero_waveform_and_iq():
    ip = os.environ.get("LAB_MMCS_IP")
    dac_id = os.environ.get("LAB_MMCS_DAC_ID")
    adc_id = os.environ.get("LAB_MMCS_ADC_ID")
    if not all((ip, dac_id, adc_id)):
        pytest.skip("LAB_MMCS_IP, LAB_MMCS_DAC_ID and LAB_MMCS_ADC_ID are required")
    program = MmcsProgram(
        master_box="box1",
        period_ns=10_000,
        repetitions=1,
        dac_programs=(
            DacProgram(
                dac_id,
                DacChannel.I,
                (DacWaveform(np.zeros(8)),),
                (PlaylistEntry(0),),
                DacPlayMode.END_WITH_ZERO,
                (TriggerEvent(40),),
            ),
        ),
        adc_programs=(
            AdcProgram(
                adc_id,
                8,
                (DemodulationWeights(0, np.zeros(8), np.zeros(8)),),
                (TriggerEvent(40),),
            ),
        ),
    )
    with MmcsHardwareDriver(MmcsVendorTransport({"box1": ip})) as driver:
        result = MmcsExecutor(driver).execute(program, timeout_s=10)
    assert result.iq_by_adc[adc_id].i_average.shape[0] == 12
