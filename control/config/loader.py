"""TOML configuration loader."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from control.core.exceptions import ConfigurationError

from .model import ControlConfig


def load_control_config(path: str | Path) -> ControlConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as stream:
            raw = tomllib.load(stream)
        return ControlConfig.model_validate(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {exc}") from exc
    except PydanticValidationError as exc:
        raise ConfigurationError(f"Invalid control config {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Cannot read control config {config_path}: {exc}") from exc
