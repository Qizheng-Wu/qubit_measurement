"""Exceptions raised by the MMCS driver."""


class MmcsError(Exception):
    """Base class for all MMCS driver errors."""


class ConnectionError(MmcsError):
    """The MMCS transport could not be connected or discovered."""


class TimeoutError(MmcsError):
    """An MMCS operation exceeded its deadline."""


class DeviceNotFoundError(MmcsError):
    """A requested board or channel was not discovered."""


class ValidationError(MmcsError, ValueError):
    """A public API value violates an MMCS hardware constraint."""


class HardwareCommandError(MmcsError):
    """The hardware rejected a command or returned an invalid response."""
