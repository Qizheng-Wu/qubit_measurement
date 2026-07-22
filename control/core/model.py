"""Shared immutable Pydantic model configuration."""

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Small common base for immutable control data models."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )
