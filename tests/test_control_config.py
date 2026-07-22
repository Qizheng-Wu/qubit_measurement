from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from control.config import MmcsDeviceConfig, SpectrumAnalyzerDeviceConfig, load_control_config
from control.core.exceptions import ConfigurationError
from control.driver.mmcs import MmcsHardwareDriver
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.factory import InstrumentFactory


VALID_CONFIG = """
schema_version = 2

[instruments.sa]
type = "spectrum_analyzer"
address = "TCPIP0::SA::INSTR"
transport_timeout_s = 12.5

[instruments.mmcs]
type = "mmcs"

[instruments.mmcs.boxes]
box1 = "192.0.2.1"
box2 = "192.0.2.2"

[instruments.mmcs.dac_boards.da_box1pcie1ch12]
sample_rate_hz = 2e9
"""


def write_config(tmp_path, content=VALID_CONFIG):
    path = tmp_path / "instruments.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_v2_defaults_and_immutable_hardware_inventory(tmp_path):
    config = load_control_config(write_config(tmp_path))
    mmcs = config.require("mmcs", MmcsDeviceConfig)
    assert config.schema_version == 2
    assert mmcs.boxes == {"box1": "192.0.2.1", "box2": "192.0.2.2"}
    assert mmcs.require_dac_board("da_box1pcie1ch12").sample_rate_hz == 2e9
    assert config.defaults.spectrum_sweep.points == 501
    assert config.defaults.spectrum_sweep.rbw_span_ratio == 0.01
    assert config.defaults.mmcs_awg.period_ns == 1_000_000
    with pytest.raises(TypeError):
        mmcs.dac_boards["new"] = mmcs.require_dac_board("da_box1pcie1ch12")
    with pytest.raises(FrozenInstanceError):
        config.defaults.mmcs_awg.period_ns = 2_000_000


def test_explicit_engineering_defaults_override_builtins(tmp_path):
    content = VALID_CONFIG + """

[defaults.spectrum_sweep]
points = 101
rbw_span_ratio = 0.02
input_attenuation_db = 30
acquisition_timeout_s = 9

[defaults.mmcs_execution]
cleanup_timeout_s = 3

[defaults.mmcs_awg]
minimum_waveform_samples = 1600
period_ns = 2_000_000
start_trigger_ns = 80
safety_margin_s = 2
"""
    config = load_control_config(write_config(tmp_path, content))
    assert config.defaults.spectrum_sweep.points == 101
    assert config.defaults.spectrum_sweep.rbw_span_ratio == 0.02
    assert config.defaults.mmcs_execution.cleanup_timeout_s == 3
    assert config.defaults.mmcs_awg.minimum_waveform_samples == 1600


def test_factory_uses_resolved_connection_and_cleanup_defaults(tmp_path):
    config = load_control_config(write_config(tmp_path))
    factory = InstrumentFactory(config)
    sa = factory.create_spectrum_analyzer("sa")
    mmcs = factory.create_mmcs("mmcs")
    assert isinstance(sa, SpectrumAnalyzerDriver)
    assert isinstance(mmcs, MmcsHardwareDriver)
    assert sa.transport.timeout_s == 12.5
    assert mmcs.shutdown_timeout_s == 5


def test_unknown_dac_board_is_configuration_error(tmp_path):
    mmcs = load_control_config(write_config(tmp_path)).require("mmcs", MmcsDeviceConfig)
    with pytest.raises(ConfigurationError, match="not configured"):
        mmcs.require_dac_board("missing")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("schema_version=1\n[instruments.x]\ntype='vna'\naddress='x'", "migrate"),
        ("schema_version=3\n[instruments.x]\ntype='vna'\naddress='x'", "expected 2"),
        ("schema_version=2\n[instruments.x]\ntype='vna'", "address"),
        ("schema_version=2\n[instruments.x]\ntype='vna'\naddress='x'\ntimeout_s=1", "unknown"),
        (
            "schema_version=2\n[instruments.m]\ntype='mmcs'\n"
            "[instruments.m.boxes]\nbox1='ip'",
            "dac_boards",
        ),
        (
            "schema_version=2\n[instruments.m]\ntype='mmcs'\n"
            "[instruments.m.boxes]\nbox1='ip'\n"
            "[instruments.m.dac_boards.da]\nsample_rate_hz=0",
            "sample_rate_hz",
        ),
        (VALID_CONFIG + "\n[defaults.mmcs_awg]\nperiod_ns=101", "multiples of 4"),
        (VALID_CONFIG + "\n[defaults.spectrum_sweep]\nextra=1", "unknown"),
    ],
)
def test_invalid_v2_config_is_rejected(tmp_path, content, message):
    with pytest.raises(ConfigurationError, match=message):
        load_control_config(write_config(tmp_path, content))


def test_missing_config_file_is_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="Cannot read"):
        load_control_config(tmp_path / "missing.toml")
