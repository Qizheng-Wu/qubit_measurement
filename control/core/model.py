"""Shared Pydantic foundations for immutable control models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError as PydanticValidationError

from control.core.exceptions import ControlError


class FrozenModel(BaseModel):
    """Strict, immutable model with temporary positional-argument compatibility.

    Pydantic models normally require keyword arguments.  The control package had
    a public dataclass API that accepted positional arguments, so retaining that
    behavior keeps the model migration source-compatible for callers.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args:
            field_names = tuple(type(self).model_fields)
            if len(args) > len(field_names):
                raise TypeError(
                    f"{type(self).__name__} expected at most {len(field_names)} "
                    f"positional arguments, got {len(args)}"
                )
            for name, value in zip(field_names, args):
                if name in kwargs:
                    raise TypeError(f"{type(self).__name__} got multiple values for {name!r}")
                kwargs[name] = value
        try:
            super().__init__(**kwargs)
        except PydanticValidationError as exc:
            errors = exc.errors()
            if errors and all(error["type"] == "missing" for error in errors):
                missing = ", ".join(str(error["loc"][0]) for error in errors)
                raise TypeError(f"{type(self).__name__} missing required argument(s): {missing}") from exc
            for error in errors:
                original = error.get("ctx", {}).get("error")
                if isinstance(original, ControlError):
                    raise original from exc
            raise

    def __setattr__(self, name: str, value: Any) -> None:
        # Preserve the mutation error exposed by the former frozen dataclasses.
        raise FrozenInstanceError(f"cannot assign to field {name!r}")
