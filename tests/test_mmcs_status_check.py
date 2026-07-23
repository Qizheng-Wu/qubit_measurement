from contextlib import contextmanager

from experiment.mmcs_status_check import check_mmcs_status


class FakeMmcsService:
    def __init__(self) -> None:
        self.events: list[str] = []

    @contextmanager
    def connected(self):
        self.events.append("connect")
        try:
            yield self
        finally:
            self.events.append("disconnect")

    def check_status(self):
        self.events.append("check-status")
        return {"status": "ok"}


def test_check_mmcs_status_owns_connection_lifecycle():
    mmcs = FakeMmcsService()

    assert check_mmcs_status(mmcs) == {"status": "ok"}
    assert mmcs.events == ["connect", "check-status", "disconnect"]
