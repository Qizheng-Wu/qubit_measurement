from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from control.db import (
    IqCalibrationRepository,
    create_calibration_engine,
    create_session_factory,
)
from control.domain.calibration import IqAutoCalibrationSpec
from control.domain.mmcs import IqCalibration, Sideband
from control.domain.power import ScalarPowerResult
from control.services.calibration import IqAutoCalibrationService


class FakeMmcs:
    def __init__(self):
        self.run_count = 0

    def check_status(self):
        return {"version": "fake"}

    @contextmanager
    def running(self, _program):
        self.run_count += 1
        yield SimpleNamespace()


class FakeSpectrum:
    driver = SimpleNamespace(identity=SimpleNamespace(raw="Fake,FPL,1,1"))

    @contextmanager
    def scalar_power_session(self, config):
        yield SimpleNamespace(config=config)


class SyntheticCalibrationService(IqAutoCalibrationService):
    def _measure_candidate(self, *, run_id, stage, spec, calibration, meter):
        frequency = meter.config.frequency_hz
        if frequency == spec.lo_frequency_hz:
            power = -90 + 2000 * (
                (calibration.i_offset - 0.035) ** 2
                + (calibration.q_offset + 0.025) ** 2
            )
        elif frequency == spec.image_frequency_hz:
            power = -100 + 200 * (
                (calibration.q_over_i_gain - 1.08) ** 2
                + (calibration.q_phase_correction_rad + 0.07) ** 2
            )
        else:
            power = -20.0
        readings = (power - 0.1, power + 40.0, power)
        self._record_evaluation(
            run_id=run_id,
            stage=stage,
            calibration=calibration,
            frequency_hz=frequency,
            readings_dbm=readings,
            objective_dbm=power,
            elapsed_s=0.001,
        )
        return power


class FailingCalibrationService(SyntheticCalibrationService):
    failure = RuntimeError("injected calibration failure")

    def _measure_candidate(self, **kwargs):
        raise self.failure


def make_spec(**updates):
    values = dict(
        signal_path="qubit_xy_q1",
        board_id="da1",
        master_box="box1",
        sample_rate_hz=500e6,
        lo_frequency_hz=5e9,
        if_frequency_hz=20e6,
        sideband=Sideband.UPPER,
        amplitude=0.02,
        minimum_samples=800,
        period_ns=1_000_000,
        start_trigger_ns=40,
        spectrum_span_hz=2e6,
        spectrum_points=201,
        resolution_bandwidth_hz=10e3,
        input_attenuation_db=20,
        measurement_timeout_s=1,
        initial_calibration=IqCalibration(),
        max_evaluations_per_stage=80,
        patience_iterations=3,
    )
    values.update(updates)
    return IqAutoCalibrationSpec(**values)


def make_service(tmp_path):
    engine = create_calibration_engine(tmp_path / "calibration.sqlite3")
    repository = IqCalibrationRepository(create_session_factory(engine))
    return engine, repository, SyntheticCalibrationService(
        FakeMmcs(), FakeSpectrum(), repository
    )


def test_two_stage_powell_recovers_four_parameters_and_full_history(tmp_path):
    toml = tmp_path / "instruments.toml"
    toml.write_text("q_over_i_gain = 1.0\n", encoding="utf-8")
    before = toml.read_bytes()
    engine, repository, service = make_service(tmp_path)

    result = service.calibrate(make_spec())

    assert result.calibration.i_offset == pytest.approx(0.035, abs=2e-3)
    assert result.calibration.q_offset == pytest.approx(-0.025, abs=2e-3)
    assert result.calibration.q_over_i_gain == pytest.approx(1.08, abs=2e-3)
    assert result.calibration.q_phase_correction_rad == pytest.approx(-0.07, abs=2e-3)
    assert result.final_lo_dbm < result.initial_lo_dbm
    assert result.final_image_dbm < result.initial_image_dbm
    assert toml.read_bytes() == before
    row = repository.get_run(result.run_id)
    assert row.status == "completed"
    assert len(row.evaluations) == (
        6 + result.offset_evaluations + result.imbalance_evaluations
    )
    assert all(len(e.readings_dbm) == 3 for e in row.evaluations)
    assert any(max(e.readings_dbm) - e.objective_dbm >= 40 for e in row.evaluations)
    assert '[instruments.mmcs.signal_paths."qubit_xy_q1"]' in result.toml_snippet(
        "qubit_xy_q1", "da1"
    )
    engine.dispose()


def test_maximum_evaluations_is_reported_as_not_converged(tmp_path):
    engine, repository, service = make_service(tmp_path)
    result = service.calibrate(make_spec(max_evaluations_per_stage=4))
    row = repository.get_run(result.run_id)
    assert result.optimizer_converged is False
    assert "maximum" in result.termination_reason.lower()
    assert row.offset_evaluations <= 4
    assert row.imbalance_evaluations <= 4
    engine.dispose()


def test_patience_stopping_path_is_persisted(tmp_path):
    engine, repository, service = make_service(tmp_path)
    result = service.calibrate(
        make_spec(patience_iterations=1, improvement_tolerance_db=0.1)
    )
    assert "improvement tolerance reached" in result.termination_reason
    assert repository.get_run(result.run_id).termination_reason == result.termination_reason
    engine.dispose()


def test_each_candidate_starts_mmcs_once_for_all_marker_repetitions(tmp_path):
    engine = create_calibration_engine(tmp_path / "calibration.sqlite3")
    repository = IqCalibrationRepository(create_session_factory(engine))
    repository.initialize()
    run_id = repository.create_run(
        signal_path="qubit_xy_q1",
        board_id="da1",
        lo_frequency_hz=5e9,
        if_frequency_hz=20e6,
        sideband="upper",
        amplitude=0.02,
        sample_rate_hz=500e6,
        initial_q_over_i_gain=1.0,
        initial_i_offset=0.0,
        initial_q_offset=0.0,
        initial_q_phase_correction_rad=0.0,
    )
    mmcs = FakeMmcs()
    service = IqAutoCalibrationService(mmcs, FakeSpectrum(), repository)

    class Meter:
        config = SimpleNamespace(frequency_hz=5e9)
        repetitions = None

        def measure(self, *, repetitions, timeout_s):
            self.repetitions = repetitions
            return ScalarPowerResult(
                frequency_hz=5e9,
                power_dbm=-70.0,
                readings_dbm=(-71.0, -70.0, -20.0),
                acquired_at=datetime.now(timezone.utc),
            )

    meter = Meter()
    power = service._measure_candidate(
        run_id=run_id,
        stage="offset",
        spec=make_spec(),
        calibration=IqCalibration(),
        meter=meter,
    )
    assert power == -70
    assert mmcs.run_count == 1
    assert meter.repetitions == 3
    assert repository.get_run(run_id).evaluations[0].readings_dbm == [-71, -70, -20]
    engine.dispose()


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (RuntimeError("failure"), "failed"),
        (KeyboardInterrupt(), "interrupted"),
    ],
)
def test_calibration_failure_state_is_persisted(tmp_path, failure, status):
    engine = create_calibration_engine(tmp_path / "calibration.sqlite3")
    repository = IqCalibrationRepository(create_session_factory(engine))
    service = FailingCalibrationService(FakeMmcs(), FakeSpectrum(), repository)
    service.failure = failure
    with pytest.raises(type(failure)):
        service.calibrate(make_spec())
    row = repository.list_runs()[0]
    assert row.status == status
    assert row.completed_at_utc is not None
    engine.dispose()
