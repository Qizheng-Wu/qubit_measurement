"""Strict TOML loader for static instrument configuration."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control.core.exceptions import ConfigurationError

from .model import (
    ControlConfig,
    DeviceConfig,
    MmcsDeviceConfig,
    SpectrumAnalyzerDeviceConfig,
    VisaConnectionConfig,
    VnaDeviceConfig,
)

_ROOT_FIELDS = {"schema_version", "instruments"}
_VISA_FIELDS = {
    "type",
    "address",
    "timeout_s",
    "read_termination",
    "write_termination",
}
_MMCS_FIELDS = {"type", "boxes", "master_box", "cleanup_timeout_s"}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{path} must be a table")
    return value


def _reject_unknown(table: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        fields = ", ".join(unknown)
        raise ConfigurationError(f"{path} contains unknown field(s): {fields}")


def _required(table: Mapping[str, Any], field: str, path: str) -> Any:
    try:
        return table[field]
    except KeyError as exc:
        raise ConfigurationError(f"{path}.{field} is required") from exc


def _parse_visa_connection(table: Mapping[str, Any], path: str) -> VisaConnectionConfig:
    address = _required(table, "address", path)
    try:
        return VisaConnectionConfig(
            address=address,
            timeout_s=table.get("timeout_s", 10.0),
            read_termination=table.get("read_termination", "\n"),
            write_termination=table.get("write_termination", "\n"),
        )
    except ConfigurationError as exc:
        raise ConfigurationError(f"{path}: {exc}") from exc


def _parse_device(name: str, raw: Any) -> DeviceConfig:
    path = f"instruments.{name}"
    table = _mapping(raw, path)
    kind = _required(table, "type", path)
    if not isinstance(kind, str):
        raise ConfigurationError(f"{path}.type must be a string")

    if kind in {"vna", "spectrum_analyzer"}:
        _reject_unknown(table, _VISA_FIELDS, path)
        connection = _parse_visa_connection(table, path)
        if kind == "vna":
            return VnaDeviceConfig(connection=connection)
        return SpectrumAnalyzerDeviceConfig(connection=connection)

    if kind == "mmcs":
        _reject_unknown(table, _MMCS_FIELDS, path)
        boxes = _required(table, "boxes", path)
        try:
            return MmcsDeviceConfig(
                boxes=_mapping(boxes, f"{path}.boxes"),
                master_box=table.get("master_box", "box1"),
                cleanup_timeout_s=table.get("cleanup_timeout_s", 5.0),
            )
        except ConfigurationError as exc:
            raise ConfigurationError(f"{path}: {exc}") from exc

    raise ConfigurationError(
        f"{path}.type has unsupported value {kind!r}; "
        "expected 'vna', 'spectrum_analyzer', or 'mmcs'"
    )


def load_control_config(path: str | Path) -> ControlConfig:
    """Load and validate an instrument configuration TOML file."""
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
    instruments_raw = _mapping(_required(root, "instruments", "root"), "instruments")
    instruments = {
        name: _parse_device(name, raw)
        for name, raw in instruments_raw.items()
    }
    return ControlConfig(schema_version=schema_version, instruments=instruments)
