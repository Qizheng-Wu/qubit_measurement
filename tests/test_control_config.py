from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from control.config import (
    MmcsDeviceConfig,
    SpectrumAnalyzerDeviceConfig,
    VnaDeviceConfig,
    load_control_config,
)
from control.core.exceptions import ConfigurationError
from control.driver.mmcs import MmcsHardwareDriver
from control.driver.spectrum_analyzer import SpectrumAnalyzerDriver
from control.driver.vna import VnaDriver
from control.factory import InstrumentFactory


VALID_CONFIG = """
schema_version = 1

[instruments.vna]
type = "vna"
address = "USB0::VNA::INSTR"
timeout_s = 12.5

[instruments.sa]
type = "spectrum_analyzer"
address = "TCPIP0::SA::INSTR"
read_termination = "\\r\\n"
write_termination = "\\n"

[instruments.mmcs]
type = "mmcs"
master_box = "box1"
cleanup_timeout_s = 3

[instruments.mmcs.boxes]
box1 = "192.0.2.1"
box2 = "192.0.2.2"
"""


def write_config(tmp_path, content: str):
    path = tmp_path / "instruments.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_valid_config_and_immutable_models(tmp_path):
    config = load_control_config(write_config(tmp_path, VALID_CONFIG))

    assert config.schema_version == 1
    assert isinstance(config.instruments["vna"], VnaDeviceConfig)
    assert isinstance(config.instruments["sa"], SpectrumAnalyzerDeviceConfig)
    mmcs = config.require("mmcs", MmcsDeviceConfig)
    assert mmcs.boxes == {"box1": "192.0.2.1", "box2": "192.0.2.2"}
    assert mmcs.cleanup_timeout_s == 3.0
    assert config.require("vna", VnaDeviceConfig).connection.timeout_s == 12.5

    with pytest.raises(TypeError):
        config.instruments["new"] = config.instruments["vna"]
    with pytest.raises(TypeError):
        mmcs.boxes["box3"] = "192.0.2.3"
    with pytest.raises(FrozenInstanceError):
        mmcs.master_box = "box2"


def test_factory_creates_correct_disconnected_drivers(tmp_path):
    config = load_control_config(write_config(tmp_path, VALID_CONFIG))
    factory = InstrumentFactory(config)

    vna = factory.create_vna("vna")
    sa = factory.create_spectrum_analyzer("sa")
    mmcs = factory.create_mmcs("mmcs")

    assert isinstance(vna, VnaDriver) and not vna.is_connected
    assert isinstance(sa, SpectrumAnalyzerDriver) and not sa.is_connected
    assert isinstance(mmcs, MmcsHardwareDriver) and not mmcs.is_connected
    assert vna.transport.resource_name == "USB0::VNA::INSTR"
    assert sa.transport.read_termination == "\r\n"
    assert mmcs.transport.boxes == {"box1": "192.0.2.1", "box2": "192.0.2.2"}


def test_factory_reports_missing_and_wrong_device_type(tmp_path):
    factory = InstrumentFactory(load_control_config(write_config(tmp_path, VALID_CONFIG)))

    with pytest.raises(ConfigurationError, match="not configured"):
        factory.create_vna("missing")
    with pytest.raises(ConfigurationError, match="expected VnaDeviceConfig"):
        factory.create_vna("sa")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("schema_version = 1\ninvalid = [", "Invalid TOML"),
        ("[instruments.vna]\ntype='vna'\naddress='x'", "schema_version"),
        ("schema_version=2\n[instruments.vna]\ntype='vna'\naddress='x'", "schema_version"),
        (
            "schema_version=1\n[instruments.x]\ntype='oscilloscope'\naddress='x'",
            "unsupported value",
        ),
        ("schema_version=1\n[instruments.x]\ntype='vna'", "address is required"),
        (
            "schema_version=1\n[instruments.x]\ntype='vna'\naddress=''",
            "non-empty string",
        ),
        (
            "schema_version=1\n[instruments.x]\ntype='vna'\naddress='x'\ntimeout_s=-1",
            "positive",
        ),
        (
            "schema_version=1\n[instruments.x]\ntype='vna'\naddress='x'\nextra=1",
            "unknown field",
        ),
        (
            "schema_version=1\n[instruments.m]\ntype='mmcs'\nmaster_box='box2'\n"
            "[instruments.m.boxes]\nbox1='192.0.2.1'",
            "master_box",
        ),
        (
            "schema_version=1\n[instruments.m]\ntype='mmcs'",
            "boxes is required",
        ),
        ("schema_version=1\nunknown=1\n[instruments.x]\ntype='vna'\naddress='x'", "unknown field"),
    ],
)
def test_invalid_config_is_rejected(tmp_path, content, message):
    with pytest.raises(ConfigurationError, match=message):
        load_control_config(write_config(tmp_path, content))


def test_missing_config_file_is_configuration_error(tmp_path):
    with pytest.raises(ConfigurationError, match="Cannot read control config"):
        load_control_config(tmp_path / "missing.toml")
