"""Instrument identity value objects."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    """Parsed response to the IEEE-488.2 ``*IDN?`` query."""

    manufacturer: str
    model: str
    serial_number: str
    firmware: str
    raw: str

    @classmethod
    def parse(cls, response: str) -> "InstrumentIdentity":
        raw = response.strip()
        fields = [field.strip() for field in raw.split(",")]
        fields.extend([""] * (4 - len(fields)))
        return cls(*fields[:4], raw=raw)
