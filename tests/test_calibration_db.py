from sqlalchemy import text

from control.core.exceptions import ConfigurationError
from control.db import (
    IqCalibrationRepository,
    create_calibration_engine,
    create_session_factory,
)


def make_repository(tmp_path):
    engine = create_calibration_engine(tmp_path / "calibration.sqlite3")
    repository = IqCalibrationRepository(create_session_factory(engine))
    return engine, repository


def run_values():
    return {
        "signal_path": "qubit_xy_q1",
        "board_id": "da1",
        "lo_frequency_hz": 5e9,
        "if_frequency_hz": 20e6,
        "sideband": "upper",
        "amplitude": 0.02,
        "sample_rate_hz": 500e6,
        "initial_q_over_i_gain": 1.0,
        "initial_i_offset": 0.0,
        "initial_q_offset": 0.0,
        "initial_q_phase_correction_rad": 0.0,
        "spectrum_analyzer_id": "FPL",
        "mmcs_version": "test",
    }


def test_repository_persists_run_evaluation_and_completion(tmp_path):
    engine, repository = make_repository(tmp_path)
    repository.initialize()
    run_id = repository.create_run(**run_values())
    evaluation_id = repository.append_evaluation(
        run_id,
        stage="offset",
        global_sequence=1,
        stage_sequence=1,
        q_over_i_gain=1.0,
        i_offset=0.01,
        q_offset=-0.02,
        q_phase_correction_rad=0.0,
        measurement_frequency_hz=5e9,
        readings_dbm=[-70, -69, -100],
        objective_dbm=-70,
        elapsed_s=0.5,
    )
    repository.complete_run(
        run_id,
        best_q_over_i_gain=1.02,
        best_i_offset=0.01,
        best_q_offset=-0.02,
        best_q_phase_correction_rad=0.03,
        optimizer_converged=True,
        termination_reason="done",
    )

    row = repository.get_run(run_id)
    assert row is not None
    assert row.status == "completed"
    assert row.completed_at_utc is not None
    assert row.best_q_over_i_gain == 1.02
    assert row.evaluations[0].id == evaluation_id
    assert row.evaluations[0].readings_dbm == [-70, -69, -100]
    assert repository.list_runs("qubit_xy_q1")[0].id == run_id
    assert repository.list_runs("missing") == ()
    engine.dispose()


def test_repository_persists_failed_and_interrupted_states(tmp_path):
    engine, repository = make_repository(tmp_path)
    repository.initialize()
    failed = repository.create_run(**run_values())
    interrupted = repository.create_run(**run_values())
    repository.fail_run(failed, "boom")
    repository.interrupt_run(interrupted, "KeyboardInterrupt")
    assert repository.get_run(failed).status == "failed"
    assert repository.get_run(failed).error_message == "boom"
    assert repository.get_run(interrupted).status == "interrupted"
    engine.dispose()


def test_schema_version_mismatch_fails_explicitly(tmp_path):
    engine, repository = make_repository(tmp_path)
    repository.initialize()
    with engine.begin() as connection:
        connection.execute(text("UPDATE schema_version SET version = 99 WHERE id = 1"))
    try:
        repository.initialize()
    except ConfigurationError as exc:
        assert "schema 99" in str(exc)
    else:
        raise AssertionError("schema mismatch was accepted")
    engine.dispose()
