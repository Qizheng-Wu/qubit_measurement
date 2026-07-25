from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from control.config import (
    ControlConfig,
    ControlDefaults,
    MmcsAwgDefaults,
    MmcsDacBoardConfig,
    MmcsDeviceConfig,
    MmcsExecutionDefaults,
    MmcsSignalPathConfig,
    SpectrumAnalyzerDeviceConfig,
    SpectrumSweepDefaults,
    VisaDeviceConfig,
    VnaDeviceConfig,
    VnaSweepDefaults,
    load_control_config,
)
from control.core.exceptions import ConfigurationError
from control.factory import InstrumentFactory
from control.services import MmcsService, SpectrumAnalyzerService


VALID_CONFIG = """
schema_version = 3

[instruments.sa]
type = "spectrum_analyzer"
address = "TCPIP0::SA::INSTR"
transport_timeout_s = 12.5
read_termination = "\\n"
write_termination = "\\n"

[instruments.mmcs]
type = "mmcs"

[instruments.mmcs.boxes]
box1 = "192.0.2.1"
box2 = "192.0.2.2"

[instruments.mmcs.dac_boards.da_box1pcie1ch12]
sample_rate_hz = 2e9

[instruments.mmcs.signal_paths.qubit_xy_q1]
dac_board_id = "da_box1pcie1ch12"
q_over_i_gain = 1.02
i_offset = 0.01
q_offset = -0.02
q_phase_correction_rad = 0.03

[defaults.vna_sweep]
points = 1001
bandwidth_hz = 1e3
averages = 1
acquisition_timeout_s = 30.0

[defaults.spectrum_sweep]
points = 501
rbw_span_ratio = 0.01
input_attenuation_db = 20.0
acquisition_timeout_s = 30.0

[defaults.mmcs_execution]
cleanup_timeout_s = 5.0

[defaults.mmcs_awg]
minimum_waveform_samples = 800
period_ns = 1_000_000
start_trigger_ns = 40
safety_margin_s = 5.0
"""


def write_config(tmp_path, content=VALID_CONFIG):
    path = tmp_path / "instruments.toml"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "model",
    (
        VisaDeviceConfig,
        VnaDeviceConfig,
        SpectrumAnalyzerDeviceConfig,
        MmcsDacBoardConfig,
        MmcsDeviceConfig,
        MmcsSignalPathConfig,
        VnaSweepDefaults,
        SpectrumSweepDefaults,
        MmcsExecutionDefaults,
        MmcsAwgDefaults,
        ControlDefaults,
        ControlConfig,
    ),
)
def test_configuration_models_have_no_field_defaults(model):
    assert all(field.is_required() for field in model.model_fields.values())


def test_load_v3_complete_config_and_immutable_hardware_inventory(tmp_path):
    config = load_control_config(write_config(tmp_path))
    mmcs = config.require("mmcs", MmcsDeviceConfig)
    assert config.schema_version == 3
    assert mmcs.boxes == {"box1": "192.0.2.1", "box2": "192.0.2.2"}
    assert mmcs.require_dac_board("da_box1pcie1ch12").sample_rate_hz == 2e9
    signal_path = mmcs.require_signal_path("qubit_xy_q1")
    assert signal_path.dac_board_id == "da_box1pcie1ch12"
    assert signal_path.q_over_i_gain == 1.02
    assert signal_path.i_offset == 0.01
    assert signal_path.q_offset == -0.02
    assert signal_path.q_phase_correction_rad == 0.03
    assert config.defaults.spectrum_sweep.points == 501
    assert config.defaults.spectrum_sweep.rbw_span_ratio == 0.01
    assert config.defaults.mmcs_awg.period_ns == 1_000_000
    sa = config.require("sa", SpectrumAnalyzerDeviceConfig)
    assert sa.transport_timeout_s == 12.5
    assert sa.read_termination == "\n"
    assert sa.write_termination == "\n"
    with pytest.raises(TypeError):
        mmcs.dac_boards["new"] = mmcs.require_dac_board("da_box1pcie1ch12")
    with pytest.raises(PydanticValidationError):
        config.defaults.mmcs_awg.period_ns = 2_000_000


def test_engineering_values_are_read_from_toml(tmp_path):
    content = (
        VALID_CONFIG.replace("points = 501", "points = 101")
        .replace("rbw_span_ratio = 0.01", "rbw_span_ratio = 0.02")
        .replace("cleanup_timeout_s = 5.0", "cleanup_timeout_s = 3.0")
        .replace("minimum_waveform_samples = 800", "minimum_waveform_samples = 1600")
    )
    config = load_control_config(write_config(tmp_path, content))
    assert config.defaults.spectrum_sweep.points == 101
    assert config.defaults.spectrum_sweep.rbw_span_ratio == 0.02
    assert config.defaults.mmcs_execution.cleanup_timeout_s == 3
    assert config.defaults.mmcs_awg.minimum_waveform_samples == 1600


def test_empty_visa_terminations_are_normalized_to_none(tmp_path):
    content = VALID_CONFIG.replace('read_termination = "\\n"', 'read_termination = ""').replace(
        'write_termination = "\\n"', 'write_termination = ""'
    )
    sa = load_control_config(write_config(tmp_path, content)).require(
        "sa", SpectrumAnalyzerDeviceConfig
    )
    assert sa.read_termination is None
    assert sa.write_termination is None


def test_factory_uses_resolved_connection_and_cleanup_defaults(tmp_path):
    config = load_control_config(write_config(tmp_path))
    factory = InstrumentFactory(config)
    sa = factory.create_spectrum_analyzer_service("sa")
    mmcs = factory.create_mmcs_service("mmcs")
    assert isinstance(sa, SpectrumAnalyzerService)
    assert isinstance(mmcs, MmcsService)
    assert sa.driver.transport.timeout_s == 12.5
    assert mmcs.driver.shutdown_timeout_s == 5


def test_unknown_dac_board_is_configuration_error(tmp_path):
    mmcs = load_control_config(write_config(tmp_path)).require("mmcs", MmcsDeviceConfig)
    with pytest.raises(ConfigurationError, match="not configured"):
        mmcs.require_dac_board("missing")


def test_unknown_signal_path_is_configuration_error(tmp_path):
    mmcs = load_control_config(write_config(tmp_path)).require("mmcs", MmcsDeviceConfig)
    with pytest.raises(ConfigurationError, match="not configured"):
        mmcs.require_signal_path("missing")


def test_signal_path_cannot_reference_unknown_board(tmp_path):
    content = VALID_CONFIG.replace(
        'dac_board_id = "da_box1pcie1ch12"',
        'dac_board_id = "missing"',
    )
    with pytest.raises(ConfigurationError, match="unknown DAC boards"):
        load_control_config(write_config(tmp_path, content))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (VALID_CONFIG.replace("schema_version = 3", "schema_version = 2"), "schema_version"),
        (VALID_CONFIG.replace("schema_version = 3", "schema_version = 4"), "schema_version"),
        (
            "schema_version=3\n[instruments.m]\ntype='mmcs'\n"
            "[instruments.m.boxes]\nbox1='ip'",
            "dac_boards",
        ),
        (
            "schema_version=3\n[instruments.m]\ntype='mmcs'\n"
            "[instruments.m.boxes]\nbox1='ip'\n"
            "[instruments.m.dac_boards.da]\nsample_rate_hz=0",
            "sample_rate_hz",
        ),
        (VALID_CONFIG.replace("period_ns = 1_000_000", "period_ns = 101"), "multiples of 4"),
        (VALID_CONFIG.replace("points = 501", "points = 501\nextra = 1"), "extra"),
    ],
)
def test_invalid_v3_config_is_rejected(tmp_path, content, message):
    with pytest.raises(ConfigurationError, match=message):
        load_control_config(write_config(tmp_path, content))


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ('type = "spectrum_analyzer"\n', "type"),
        ("transport_timeout_s = 12.5\n", "transport_timeout_s"),
        ('read_termination = "\\n"\n', "read_termination"),
        ('write_termination = "\\n"\n', "write_termination"),
        ("points = 1001\n", "points"),
        ("bandwidth_hz = 1e3\n", "bandwidth_hz"),
        ("averages = 1\n", "averages"),
        ("points = 501\n", "points"),
        ("rbw_span_ratio = 0.01\n", "rbw_span_ratio"),
        ("input_attenuation_db = 20.0\n", "input_attenuation_db"),
        ("cleanup_timeout_s = 5.0\n", "cleanup_timeout_s"),
        ("minimum_waveform_samples = 800\n", "minimum_waveform_samples"),
        ("period_ns = 1_000_000\n", "period_ns"),
        ("start_trigger_ns = 40\n", "start_trigger_ns"),
        ("safety_margin_s = 5.0\n", "safety_margin_s"),
    ],
)
def test_required_runtime_field_cannot_be_omitted(tmp_path, fragment, message):
    content = VALID_CONFIG.replace(fragment, "", 1)
    with pytest.raises(ConfigurationError, match=message):
        load_control_config(write_config(tmp_path, content))


@pytest.mark.parametrize(
    ("start_marker", "end_marker", "message"),
    [
        ("[defaults.vna_sweep]", "[defaults.spectrum_sweep]", "vna_sweep"),
        ("[defaults.spectrum_sweep]", "[defaults.mmcs_execution]", "spectrum_sweep"),
        ("[defaults.mmcs_execution]", "[defaults.mmcs_awg]", "mmcs_execution"),
        ("[defaults.mmcs_awg]", None, "mmcs_awg"),
    ],
)
def test_defaults_subsection_cannot_be_omitted(
    tmp_path, start_marker, end_marker, message
):
    start = VALID_CONFIG.index(start_marker)
    end = VALID_CONFIG.index(end_marker, start) if end_marker else len(VALID_CONFIG)
    content = VALID_CONFIG[:start] + VALID_CONFIG[end:]
    with pytest.raises(ConfigurationError, match=message):
        load_control_config(write_config(tmp_path, content))


def test_defaults_section_cannot_be_omitted(tmp_path):
    content = VALID_CONFIG[: VALID_CONFIG.index("[defaults.vna_sweep]")]
    with pytest.raises(ConfigurationError, match="defaults"):
        load_control_config(write_config(tmp_path, content))


def test_missing_config_file_is_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="Cannot read"):
        load_control_config(tmp_path / "missing.toml")
