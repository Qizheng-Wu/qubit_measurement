"""Shared configuration entry point for experiment modules."""

from __future__ import annotations

from pathlib import Path

from control.config import ControlConfig, load_control_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "instruments.local.toml"


def load_config(path: str | Path | None = None) -> ControlConfig:
    """Load the default project configuration or an explicit TOML file."""

    return load_control_config(DEFAULT_CONFIG_PATH if path is None else path)
