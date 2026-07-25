"""Explicitly enabled laboratory hardware smoke tests."""

from __future__ import annotations

import os

import numpy as np
import pytest

from control.domain.mmcs import (
    AdcProgram,
    DacChannel,
    DacPlayMode,
    DacBoardProgram,
    DacChannelProgram,
    DacWaveform,
    DemodulationWeights,
    MmcsProgram,
    PlaylistEntry,
    SingleToneSpec,
    TriggerEvent,
    TriggerCommand,
)
from control.domain.sweep import SpectrumSweepConfig, VnaSweepConfig
from control.domain.power import ScalarPowerMeasurementConfig
from control.domain.calibration import IqAutoCalibrationSpec
from control.domain.mmcs import IqCalibration, Sideband
from control.db import IqCalibrationRepository, create_calibration_engine, create_session_factory
from control.driver.mmcs import MmcsHardwareDriver
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver
from control.transport.mmcs_vendor import MmcsVendorTransport
from control.transport.visa import VisaTransport
from control.config import MmcsDeviceConfig, load_control_config
from control.factory import InstrumentFactory
from control.services import (
    MmcsService,
    SpectrumAnalyzerService,
    VnaService,
    build_cyclic_dac_program,
    generate_single_tone,
    IqAutoCalibrationService,
)


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
    service = VnaService(
        VnaDriver(VisaTransport(resource, timeout_s=10, read_termination="\n", write_termination="\n"))
    )
    with service.connected():
        with service.running(VnaSweepConfig(
                start_hz=4e9, stop_hz=4.01e9, points=11,
                bandwidth_hz=1e5, power_dbm=-60, averages=1,
        )) as run:
            trace = run.result(timeout_s=30)
    assert trace.s_parameter.shape == (11,)


def test_spectrum_analyzer_short_sweep():
    resource = os.environ.get("LAB_SA_RESOURCE")
    if not resource:
        pytest.skip("LAB_SA_RESOURCE is not configured")
    service = SpectrumAnalyzerService(
        SpectrumAnalyzerDriver(VisaTransport(resource, timeout_s=10, read_termination="\n", write_termination="\n"))
    )
    with service.connected():
        with service.running(SpectrumSweepConfig(
                start_hz=4e9, stop_hz=4.01e9, points=11,
                resolution_bandwidth_hz=1e5, input_attenuation_db=20,
        )) as run:
            trace = run.result(timeout_s=30)
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
        dac_boards=(
            DacBoardProgram(
                board_id=dac_id,
                triggers=(TriggerEvent(time_ns=40, command=TriggerCommand.START),),
                channels=tuple(
                    DacChannelProgram(
                        channel=channel,
                        waveforms=(DacWaveform(samples=np.zeros(8)),),
                        playlist=(
                            PlaylistEntry(waveform_index=0, trigger=TriggerCommand.START),
                        ),
                        play_mode=DacPlayMode.END_WITH_ZERO,
                    )
                    for channel in DacChannel
                ),
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
    service = MmcsService(
        MmcsHardwareDriver(MmcsVendorTransport({"box1": ip}), shutdown_timeout_s=5),
        cleanup_timeout_s=5,
    )
    with service.connected():
        with service.running(program) as run:
            result = run.result(timeout_s=10)
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
    config = load_control_config(config_path)
    board = config.require(mmcs_name, MmcsDeviceConfig).require_dac_board(dac_id)
    spectrum_defaults = config.defaults.spectrum_sweep
    awg_defaults = config.defaults.mmcs_awg
    tone = generate_single_tone(
        SingleToneSpec(
            sample_rate_hz=board.sample_rate_hz,
            frequency_hz=20e6,
            amplitude=0.02,
            phase_rad=0.0,
            minimum_samples=awg_defaults.minimum_waveform_samples,
        )
    )
    timeout = spectrum_defaults.acquisition_timeout_s
    program = build_cyclic_dac_program(
        tone.waveform,
        board_id=dac_id,
        channel=DacChannel.I,
        master_box=master_box,
        run_duration_s=timeout + awg_defaults.safety_margin_s,
        period_ns=awg_defaults.period_ns,
        start_trigger_ns=awg_defaults.start_trigger_ns,
    )
    spectrum_config = SpectrumSweepConfig.from_center_span(
        center_hz=tone.actual_frequency_hz,
        span_hz=2e6,
        points=spectrum_defaults.points,
        resolution_bandwidth_hz=2e6 * spectrum_defaults.rbw_span_ratio,
        input_attenuation_db=spectrum_defaults.input_attenuation_db,
    )
    factory = InstrumentFactory(config)
    mmcs = factory.create_mmcs_service(mmcs_name)
    spectrum = factory.create_spectrum_analyzer_service(spectrum_name)
    with mmcs.connected(), spectrum.connected():
        with mmcs.running(program):
            with spectrum.running(spectrum_config) as run:
                trace = run.result(timeout_s=timeout)
            with spectrum.scalar_power_session(ScalarPowerMeasurementConfig(
                frequency_hz=tone.actual_frequency_hz,
                span_hz=2e6,
                points=spectrum_defaults.points,
                resolution_bandwidth_hz=2e6 * spectrum_defaults.rbw_span_ratio,
                input_attenuation_db=spectrum_defaults.input_attenuation_db,
            )) as meter:
                marker = meter.measure(repetitions=3, timeout_s=timeout)
    assert np.all(np.isfinite(trace.power_dbm))
    assert marker.power_dbm == pytest.approx(float(np.max(trace.power_dbm)), abs=5.0)


def test_iq_auto_calibration_low_evaluation_end_to_end(tmp_path):
    config_path = os.environ.get("LAB_CONTROL_CONFIG")
    mmcs_name = os.environ.get("LAB_MMCS_NAME")
    spectrum_name = os.environ.get("LAB_SA_NAME")
    master_box = os.environ.get("LAB_MMCS_MASTER_BOX")
    signal_path_name = os.environ.get("LAB_MMCS_SIGNAL_PATH")
    lo_hz = os.environ.get("LAB_IQ_LO_HZ")
    if not all((config_path, mmcs_name, spectrum_name, master_box, signal_path_name, lo_hz)):
        pytest.skip(
            "LAB_CONTROL_CONFIG, LAB_MMCS_NAME, LAB_SA_NAME, LAB_MMCS_MASTER_BOX, "
            "LAB_MMCS_SIGNAL_PATH and LAB_IQ_LO_HZ are required"
        )
    config = load_control_config(config_path)
    mmcs_config = config.require(mmcs_name, MmcsDeviceConfig)
    signal_path = mmcs_config.require_signal_path(signal_path_name)
    board = mmcs_config.require_dac_board(signal_path.dac_board_id)
    awg = config.defaults.mmcs_awg
    factory = InstrumentFactory(config)
    mmcs = factory.create_mmcs_service(mmcs_name)
    spectrum = factory.create_spectrum_analyzer_service(spectrum_name)
    engine = create_calibration_engine(tmp_path / "hardware-calibration.sqlite3")
    repository = IqCalibrationRepository(create_session_factory(engine))
    service = IqAutoCalibrationService(mmcs, spectrum, repository)
    spec = IqAutoCalibrationSpec(
        signal_path=signal_path_name,
        board_id=signal_path.dac_board_id,
        master_box=master_box,
        sample_rate_hz=board.sample_rate_hz,
        lo_frequency_hz=float(lo_hz),
        if_frequency_hz=float(os.environ.get("LAB_IQ_IF_HZ", "20000000")),
        sideband=Sideband(os.environ.get("LAB_IQ_SIDEBAND", "upper")),
        amplitude=float(os.environ.get("LAB_IQ_AMPLITUDE", "0.01")),
        minimum_samples=awg.minimum_waveform_samples,
        period_ns=awg.period_ns,
        start_trigger_ns=awg.start_trigger_ns,
        spectrum_span_hz=2e6,
        spectrum_points=101,
        resolution_bandwidth_hz=10e3,
        input_attenuation_db=20,
        measurement_timeout_s=10,
        initial_calibration=IqCalibration(
            q_over_i_gain=signal_path.q_over_i_gain,
            i_offset=signal_path.i_offset,
            q_offset=signal_path.q_offset,
            q_phase_correction_rad=signal_path.q_phase_correction_rad,
        ),
        max_evaluations_per_stage=4,
    )
    try:
        with mmcs.connected(), spectrum.connected():
            result = service.calibrate(spec)
        assert repository.get_run(result.run_id).status == "completed"
    finally:
        engine.dispose()
