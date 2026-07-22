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
    SingleToneSpec,
    build_cyclic_dac_program,
    generate_single_tone,
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
from experiment.mmcs_awg_spectrum import acquire_spectrum_while_mmcs_runs


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


def test_mmcs_awg_visible_on_spectrum_analyzer():
    ip = os.environ.get("LAB_MMCS_IP")
    dac_id = os.environ.get("LAB_MMCS_DAC_ID")
    sample_rate = os.environ.get("LAB_MMCS_DAC_SAMPLE_RATE_HZ")
    spectrum_resource = os.environ.get("LAB_SA_RESOURCE")
    if not all((ip, dac_id, sample_rate, spectrum_resource)):
        pytest.skip(
            "LAB_MMCS_IP, LAB_MMCS_DAC_ID, LAB_MMCS_DAC_SAMPLE_RATE_HZ, "
            "and LAB_SA_RESOURCE are required"
        )

    tone = generate_single_tone(
        SingleToneSpec(
            sample_rate_hz=float(sample_rate),
            frequency_hz=20e6,
            amplitude=0.02,
        )
    )
    program = build_cyclic_dac_program(
        tone.waveform,
        board_id=dac_id,
        channel=DacChannel.I,
        master_box="box1",
        run_duration_s=15,
    )
    sweep = SpectrumSweepConfig.from_center_span(
        center_hz=tone.actual_frequency_hz,
        span_hz=2e6,
        points=11,
        resolution_bandwidth_hz=100e3,
        input_attenuation_db=20,
    )

    with MmcsHardwareDriver(MmcsVendorTransport({"box1": ip})) as mmcs_driver:
        with SpectrumAnalyzerDriver(VisaTransport(spectrum_resource)) as analyzer_driver:
            trace = acquire_spectrum_while_mmcs_runs(
                MmcsExecutor(mmcs_driver),
                SpectrumAnalyzerController(analyzer_driver),
                program=program,
                spectrum_config=sweep,
                spectrum_timeout_s=10,
            )

    assert trace.power_dbm.shape == (11,)
    assert np.all(np.isfinite(trace.power_dbm))
