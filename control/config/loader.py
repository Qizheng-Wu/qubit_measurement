"""Strict TOML loader for schema version 2."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control.core.exceptions import ConfigurationError

from .model import (
    ControlConfig, ControlDefaults, DeviceConfig, MmcsAwgDefaults,
    MmcsDacBoardConfig, MmcsDeviceConfig, MmcsExecutionDefaults,
    SpectrumAnalyzerDeviceConfig, SpectrumSweepDefaults, VisaConnectionConfig,
    VnaDeviceConfig, VnaSweepDefaults,
)

_ROOT_FIELDS = {"schema_version", "instruments", "defaults"}
_VISA_FIELDS = {"type", "address", "transport_timeout_s", "read_termination", "write_termination"}
_MMCS_FIELDS = {"type", "boxes", "dac_boards"}
_DEFAULT_FIELDS = {
    "vna_sweep": {"points", "bandwidth_hz", "averages", "acquisition_timeout_s"},
    "spectrum_sweep": {"points", "rbw_span_ratio", "input_attenuation_db", "acquisition_timeout_s"},
    "mmcs_execution": {"cleanup_timeout_s"},
    "mmcs_awg": {"minimum_waveform_samples", "period_ns", "start_trigger_ns", "safety_margin_s"},
}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{path} must be a table")
    return value


def _reject_unknown(table: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigurationError(f"{path} contains unknown field(s): {', '.join(unknown)}")


def _required(table: Mapping[str, Any], field: str, path: str) -> Any:
    try:
        return table[field]
    except KeyError as exc:
        raise ConfigurationError(f"{path}.{field} is required") from exc


def _construct(factory, values: Mapping[str, Any], path: str):
    try:
        return factory(**dict(values))
    except (ConfigurationError, TypeError) as exc:
        raise ConfigurationError(f"{path}: {exc}") from exc


def _parse_device(name: str, raw: Any) -> DeviceConfig:
    path = f"instruments.{name}"
    table = _mapping(raw, path)
    kind = _required(table, "type", path)
    if not isinstance(kind, str):
        raise ConfigurationError(f"{path}.type must be a string")
    if kind in {"vna", "spectrum_analyzer"}:
        _reject_unknown(table, _VISA_FIELDS, path)
        values = {key: value for key, value in table.items() if key != "type"}
        connection = _construct(VisaConnectionConfig, values, path)
        return VnaDeviceConfig(connection) if kind == "vna" else SpectrumAnalyzerDeviceConfig(connection)
    if kind == "mmcs":
        _reject_unknown(table, _MMCS_FIELDS, path)
        boxes = _mapping(_required(table, "boxes", path), f"{path}.boxes")
        boards_raw = _mapping(_required(table, "dac_boards", path), f"{path}.dac_boards")
        boards = {}
        for board_id, board_raw in boards_raw.items():
            board_path = f"{path}.dac_boards.{board_id}"
            board_table = _mapping(board_raw, board_path)
            _reject_unknown(board_table, {"sample_rate_hz"}, board_path)
            boards[board_id] = _construct(MmcsDacBoardConfig, board_table, board_path)
        return _construct(MmcsDeviceConfig, {"boxes": boxes, "dac_boards": boards}, path)
    raise ConfigurationError(
        f"{path}.type has unsupported value {kind!r}; expected 'vna', 'spectrum_analyzer', or 'mmcs'"
    )


def _parse_defaults(raw: Any) -> ControlDefaults:
    table = _mapping(raw, "defaults")
    _reject_unknown(table, set(_DEFAULT_FIELDS), "defaults")
    factories = {
        "vna_sweep": VnaSweepDefaults,
        "spectrum_sweep": SpectrumSweepDefaults,
        "mmcs_execution": MmcsExecutionDefaults,
        "mmcs_awg": MmcsAwgDefaults,
    }
    parsed = {}
    for name, factory in factories.items():
        section = _mapping(table.get(name, {}), f"defaults.{name}")
        _reject_unknown(section, _DEFAULT_FIELDS[name], f"defaults.{name}")
        parsed[name] = _construct(factory, section, f"defaults.{name}")
    return ControlDefaults(**parsed)


def load_control_config(path: str | Path) -> ControlConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as stream:
            root = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Cannot read control config {config_path}: {exc}") from exc
    _reject_unknown(root, _ROOT_FIELDS, "root")
    schema_version = _required(root, "schema_version", "root")
    if schema_version == 1:
        raise ConfigurationError("schema_version 1 is no longer supported; migrate to schema_version 2")
    instruments_raw = _mapping(_required(root, "instruments", "root"), "instruments")
    instruments = {name: _parse_device(name, raw) for name, raw in instruments_raw.items()}
    return ControlConfig(schema_version, instruments, _parse_defaults(root.get("defaults", {})))
