"""Transactional repository for IQ calibration history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from control.core.exceptions import ConfigurationError

from .models import (
    Base,
    IqCalibrationEvaluationOrm,
    IqCalibrationRunOrm,
    SchemaVersionOrm,
)

SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IqCalibrationRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def initialize(self) -> None:
        engine = self._sessions.kw["bind"]
        if inspect(engine).has_table(SchemaVersionOrm.__tablename__):
            with self._sessions() as session:
                row = session.get(SchemaVersionOrm, 1)
            if row is None:
                raise ConfigurationError(
                    "Calibration database has no schema version row"
                )
            if row.version != SCHEMA_VERSION:
                raise ConfigurationError(
                    f"Unsupported calibration database schema {row.version}; "
                    f"expected {SCHEMA_VERSION}"
                )
            Base.metadata.create_all(engine)
            return

        Base.metadata.create_all(engine)
        with self._sessions.begin() as session:
            session.add(SchemaVersionOrm(id=1, version=SCHEMA_VERSION))

    def create_run(self, **values: Any) -> int:
        with self._sessions.begin() as session:
            row = IqCalibrationRunOrm(
                **values,
                status="running",
                created_at_utc=_utc_now(),
            )
            session.add(row)
            session.flush()
            return row.id

    def append_evaluation(self, run_id: int, **values: Any) -> int:
        with self._sessions.begin() as session:
            if session.get(IqCalibrationRunOrm, run_id) is None:
                raise KeyError(f"Unknown IQ calibration run {run_id}")
            row = IqCalibrationEvaluationOrm(
                run_id=run_id,
                **values,
                created_at_utc=_utc_now(),
            )
            session.add(row)
            session.flush()
            return row.id

    def _finish(self, run_id: int, *, status: str, **values: Any) -> None:
        with self._sessions.begin() as session:
            row = session.get(IqCalibrationRunOrm, run_id)
            if row is None:
                raise KeyError(f"Unknown IQ calibration run {run_id}")
            for key, value in values.items():
                setattr(row, key, value)
            row.status = status
            row.completed_at_utc = _utc_now()

    def complete_run(self, run_id: int, **values: Any) -> None:
        self._finish(run_id, status="completed", **values)

    def fail_run(self, run_id: int, error_message: str, **values: Any) -> None:
        self._finish(
            run_id,
            status="failed",
            error_message=error_message,
            **values,
        )

    def interrupt_run(self, run_id: int, error_message: str, **values: Any) -> None:
        self._finish(
            run_id,
            status="interrupted",
            error_message=error_message,
            **values,
        )

    def get_run(self, run_id: int) -> IqCalibrationRunOrm | None:
        with self._sessions() as session:
            return session.scalar(
                select(IqCalibrationRunOrm)
                .options(selectinload(IqCalibrationRunOrm.evaluations))
                .where(IqCalibrationRunOrm.id == run_id)
            )

    def list_runs(self, signal_path: str | None = None) -> tuple[IqCalibrationRunOrm, ...]:
        statement = select(IqCalibrationRunOrm).order_by(IqCalibrationRunOrm.id.desc())
        if signal_path is not None:
            statement = statement.where(IqCalibrationRunOrm.signal_path == signal_path)
        with self._sessions() as session:
            return tuple(session.scalars(statement))
