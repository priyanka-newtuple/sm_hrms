from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from background_jobs.db_models import ActionRunModel, BackgroundJobsModelService, _strip_null_bytes


def test_strip_null_bytes_removes_nul_from_nested_strings() -> None:
    poisoned = {
        "files": [{"filename": "ok.pdf"}],
        "drafts": [{"data": {"invoice_number": "IG52PJ4I\x00garbage"}}],
    }

    cleaned = _strip_null_bytes(poisoned)

    assert cleaned["drafts"][0]["data"]["invoice_number"] == "IG52PJ4Igarbage"
    assert cleaned["files"][0]["filename"] == "ok.pdf"


def test_strip_null_bytes_leaves_clean_values_untouched() -> None:
    clean = {"a": "b", "n": 3, "list": [1, "two", None]}

    assert _strip_null_bytes(clean) == clean


class _FakeDb:
    """In-memory stand-in for a SQLAlchemy session."""

    def __init__(self) -> None:
        self._runs: dict[str, ActionRunModel] = {}

    def query(self, model):
        return _FakeQuery(self._runs)

    def add(self, obj: Any) -> None:
        if isinstance(obj, ActionRunModel):
            self._runs[obj.run_id] = obj

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def refresh(self, obj: Any) -> None:
        pass


class _FakeQuery:
    def __init__(self, runs: dict[str, ActionRunModel]) -> None:
        self._runs = runs
        self._filters: list[Any] = []

    def filter(self, *args: Any) -> _FakeQuery:
        return self

    def order_by(self, *args: Any) -> _FakeQuery:
        return self

    def limit(self, n: int) -> _FakeQuery:
        return self

    def all(self) -> list[ActionRunModel]:
        return list(self._runs.values())

    def first(self) -> ActionRunModel | None:
        return next(iter(self._runs.values()), None)

    def count(self) -> int:
        return len(self._runs)

    def update(self, values: dict[str, Any], synchronize_session: bool = False) -> int:
        row = self.first()
        if row is None:
            return 0
        for key, value in values.items():
            setattr(row, key, value)
        return 1


def _make_run(run_id: str = "run-1", status: str = "pending") -> ActionRunModel:
    run = ActionRunModel()
    run.run_id = run_id
    run.organization_id = "org-1"
    run.entity_id = "entity-1"
    run.action_kind = "mail.send_email"
    run.config_json = {"to": "test@example.com"}
    run.resolved_config_json = None
    run.status = status
    run.outcome = None
    run.attempts = 0
    run.idempotency_key = None
    run.scheduled_at = None
    run.external_timeout_at = None
    run.created_at = datetime.now(UTC)
    run.updated_at = datetime.now(UTC)
    run.completed_at = None
    return run


def test_mark_action_run_running_updates_status() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "pending")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    claimed = service.mark_action_run_running(db, "run-1")

    assert claimed is True
    assert db._runs["run-1"].status == "running"


def test_mark_action_run_result_sets_succeeded() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "running")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    service.mark_action_run_result(db, "run-1", "succeeded", "sent", "{}")

    assert db._runs["run-1"].status == "succeeded"
    assert db._runs["run-1"].outcome == "sent"
    assert db._runs["run-1"].completed_at is not None


def test_mark_action_run_result_sets_failed() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "running")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    service.mark_action_run_result(db, "run-1", "failed", "send_error", "{}")

    assert db._runs["run-1"].status == "failed"
    assert db._runs["run-1"].outcome == "send_error"


def test_mark_action_run_pending_external() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "running")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    service.mark_action_run_pending_external(db, "run-1", "sent", "{}")

    assert db._runs["run-1"].status == "pending_external"
    assert db._runs["run-1"].outcome == "sent"
    assert db._runs["run-1"].completed_at is None


def test_increment_action_run_attempts() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "pending")
    run.attempts = 0
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    new_count = service.increment_action_run_attempts(db, "run-1")

    assert new_count == 1
    assert db._runs["run-1"].attempts == 1


def test_schedule_action_run_retry_sets_scheduled_at() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "running")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    service.schedule_action_run_retry(db, "run-1", "send_error", "{}", delay_seconds=60)

    assert db._runs["run-1"].status == "pending"
    assert db._runs["run-1"].scheduled_at is not None


def test_get_action_run_returns_correct_fields() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "succeeded")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    result = service.get_action_run(db, "run-1")

    assert result is not None
    assert result["run_id"] == "run-1"
    assert result["organization_id"] == "org-1"
    assert result["entity_id"] == "entity-1"
    assert result["action_kind"] == "mail.send_email"
    assert result["status"] == "succeeded"


def test_get_action_run_returns_none_for_missing_run() -> None:
    db = _FakeDb()
    service = BackgroundJobsModelService()
    result = service.get_action_run(db, "nonexistent-run")
    assert result is None


def test_update_action_run_submitted_marks_succeeded() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "pending_external")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    service.update_action_run_submitted(db, "run-1", {"name": "John", "email": "john@example.com"})

    assert db._runs["run-1"].status == "succeeded"
    assert db._runs["run-1"].outcome == "received"
    assert db._runs["run-1"].completed_at is not None


def test_timeout_pending_external_runs_marks_failed() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "pending_external")
    run.external_timeout_at = datetime.now(UTC) - timedelta(hours=1)
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    timed_out = service.timeout_pending_external_runs(db)

    assert "run-1" in timed_out
    assert db._runs["run-1"].status == "failed"
    assert db._runs["run-1"].outcome == "timeout"


def test_mark_action_run_failed_sets_status() -> None:
    db = _FakeDb()
    run = _make_run("run-1", "running")
    db._runs["run-1"] = run

    service = BackgroundJobsModelService()
    service.mark_action_run_failed(db, "run-1", "executor_error")

    assert db._runs["run-1"].status == "failed"
    assert db._runs["run-1"].outcome == "executor_error"
    assert db._runs["run-1"].completed_at is not None
