"""Instrument identity value objects."""

from control.core.model import FrozenModel


class InstrumentIdentity(FrozenModel):
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
        return cls(
            manufacturer=fields[0],
            model=fields[1],
            serial_number=fields[2],
            firmware=fields[3],
            raw=raw,
        )
