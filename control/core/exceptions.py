"""Project-owned exception hierarchy for instrument control."""


class ControlError(Exception):
    """Base class for all errors raised by :mod:`control`."""


class ConfigurationError(ControlError):
    """Static configuration is missing or inconsistent."""


class ValidationError(ControlError, ValueError):
    """A requested operation violates a domain or hardware constraint."""


class ConnectionError(ControlError):
    """An instrument connection could not be established or used."""


class TransportTimeoutError(ConnectionError, TimeoutError):
    """A transport operation exceeded its explicit deadline."""


class ProtocolError(ControlError):
    """An instrument returned a malformed or unexpected response."""


class InstrumentCommandError(ControlError):
    """An instrument rejected or failed to execute a command."""


class InstrumentStateError(ControlError):
    """An operation is invalid in the instrument's current state."""


class AcquisitionError(ControlError):
    """A configured measurement failed to produce a valid result."""
