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
    MmcsProgram,
    PlaylistEntry,
    TriggerEvent,
    TriggerCommand,
)
from control.domain.sweep import SpectrumSweepConfig, VnaSweepConfig
from control.driver.mmcs import MmcsHardwareDriver
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver
from control.transport.mmcs_vendor import MmcsVendorTransport
from control.transport.visa import VisaTransport
from control.application import (
    MmcsAwgSpectrumExperiment,
    MmcsAwgSpectrumSpec,
    MmcsExecutor,
    SpectrumAnalyzerController,
    VnaController,
)
from control.config import load_control_config


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
    with VnaDriver(VisaTransport(resource, timeout_s=10, read_termination="\n", write_termination="\n")) as driver:
        trace = VnaController(driver).acquire(
            VnaSweepConfig(
                start_hz=4e9, stop_hz=4.01e9, points=11,
                bandwidth_hz=1e5, power_dbm=-60, averages=1,
            ),
            timeout_s=30,
        )
    assert trace.s_parameter.shape == (11,)


def test_spectrum_analyzer_short_sweep():
    resource = os.environ.get("LAB_SA_RESOURCE")
    if not resource:
        pytest.skip("LAB_SA_RESOURCE is not configured")
    with SpectrumAnalyzerDriver(VisaTransport(resource, timeout_s=10, read_termination="\n", write_termination="\n")) as driver:
        trace = SpectrumAnalyzerController(driver).acquire(
            SpectrumSweepConfig(
                start_hz=4e9, stop_hz=4.01e9, points=11,
                resolution_bandwidth_hz=1e5, input_attenuation_db=20,
            ),
            timeout_s=30,
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
                board_id=dac_id,
                channel=DacChannel.I,
                waveforms=(DacWaveform(samples=np.zeros(8)),),
                playlist=(PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),),
                play_mode=DacPlayMode.END_WITH_ZERO,
                triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
            ),
        ),
        adc_programs=(
            AdcProgram(
                board_id=adc_id,
                sample_length=8,
                demodulations=(
                    DemodulationWeights(channel=0, i=np.zeros(8), q=np.zeros(8)),
                ),
                triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
            ),
        ),
    )
    with MmcsHardwareDriver(MmcsVendorTransport({"box1": ip}), shutdown_timeout_s=5) as driver:
        result = MmcsExecutor(driver, cleanup_timeout_s=5).execute(program, timeout_s=10)
    assert result.iq_by_adc[adc_id].i_average.shape[0] == 12


def test_mmcs_awg_visible_on_spectrum_analyzer():
    config_path = os.environ.get("LAB_CONTROL_CONFIG")
    mmcs_name = os.environ.get("LAB_MMCS_NAME")
    spectrum_name = os.environ.get("LAB_SA_NAME")
    master_box = os.environ.get("LAB_MMCS_MASTER_BOX")
    dac_id = os.environ.get("LAB_MMCS_DAC_ID")
    if not all((config_path, mmcs_name, spectrum_name, master_box, dac_id)):
        pytest.skip(
            "LAB_CONTROL_CONFIG, LAB_MMCS_NAME, LAB_SA_NAME, LAB_MMCS_MASTER_BOX, "
            "and LAB_MMCS_DAC_ID are required"
        )
    result = MmcsAwgSpectrumExperiment(load_control_config(config_path)).acquire(
        MmcsAwgSpectrumSpec(
            mmcs_name=mmcs_name,
            spectrum_analyzer_name=spectrum_name,
            master_box=master_box,
            dac_board_id=dac_id,
            dac_channel=DacChannel.I,
            tone_frequency_hz=20e6,
            tone_amplitude=0.02,
            tone_phase_rad=0.0,
            spectrum_span_hz=2e6,
        )
    )
    assert np.all(np.isfinite(result.trace.power_dbm))
