"""SQLAlchemy models for IQ calibration history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SchemaVersionOrm(Base):
    __tablename__ = "schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class IqCalibrationRunOrm(Base):
    __tablename__ = "iq_calibration_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_path: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    board_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lo_frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)
    if_frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)
    sideband: Mapped[str] = mapped_column(String(16), nullable=False)
    amplitude: Mapped[float] = mapped_column(Float, nullable=False)
    sample_rate_hz: Mapped[float] = mapped_column(Float, nullable=False)

    initial_q_over_i_gain: Mapped[float] = mapped_column(Float, nullable=False)
    initial_i_offset: Mapped[float] = mapped_column(Float, nullable=False)
    initial_q_offset: Mapped[float] = mapped_column(Float, nullable=False)
    initial_q_phase_correction_rad: Mapped[float] = mapped_column(Float, nullable=False)

    best_q_over_i_gain: Mapped[float | None] = mapped_column(Float)
    best_i_offset: Mapped[float | None] = mapped_column(Float)
    best_q_offset: Mapped[float | None] = mapped_column(Float)
    best_q_phase_correction_rad: Mapped[float | None] = mapped_column(Float)

    initial_lo_dbm: Mapped[float | None] = mapped_column(Float)
    initial_target_dbm: Mapped[float | None] = mapped_column(Float)
    initial_image_dbm: Mapped[float | None] = mapped_column(Float)
    final_lo_dbm: Mapped[float | None] = mapped_column(Float)
    final_target_dbm: Mapped[float | None] = mapped_column(Float)
    final_image_dbm: Mapped[float | None] = mapped_column(Float)
    lo_improvement_db: Mapped[float | None] = mapped_column(Float)
    image_improvement_db: Mapped[float | None] = mapped_column(Float)
    image_rejection_db: Mapped[float | None] = mapped_column(Float)

    offset_evaluations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imbalance_evaluations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    optimizer_converged: Mapped[bool | None] = mapped_column(Boolean)
    termination_reason: Mapped[str | None] = mapped_column(Text)
    spectrum_analyzer_id: Mapped[str | None] = mapped_column(Text)
    mmcs_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    evaluations: Mapped[list["IqCalibrationEvaluationOrm"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="IqCalibrationEvaluationOrm.global_sequence",
    )


class IqCalibrationEvaluationOrm(Base):
    __tablename__ = "iq_calibration_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("iq_calibration_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    global_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    q_over_i_gain: Mapped[float] = mapped_column(Float, nullable=False)
    i_offset: Mapped[float] = mapped_column(Float, nullable=False)
    q_offset: Mapped[float] = mapped_column(Float, nullable=False)
    q_phase_correction_rad: Mapped[float] = mapped_column(Float, nullable=False)
    measurement_frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)
    readings_dbm: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    objective_dbm: Mapped[float] = mapped_column(Float, nullable=False)
    elapsed_s: Mapped[float] = mapped_column(Float, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped[IqCalibrationRunOrm] = relationship(back_populates="evaluations")
