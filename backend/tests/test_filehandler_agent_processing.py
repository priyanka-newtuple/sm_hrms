"""Unit tests for filehandler agent-processing trigger helpers."""

from __future__ import annotations

from filehandler.manager import FilehandlerServiceManager
from filehandler.models.interface import FileRecordStatus

def test_agent_processing_enabled_coercion() -> None:
    enabled = FilehandlerServiceManager._agent_processing_enabled
    assert enabled({"agent_processing_enabled": True}) is True
    assert enabled({"agent_processing_enabled": "true"}) is True
    assert enabled({"agent_processing_enabled": "1"}) is True
    assert enabled({"agent_processing_enabled": "on"}) is True
    assert enabled({"agent_processing_enabled": False}) is False
    assert enabled({"agent_processing_enabled": "no"}) is False
    assert enabled({}) is False


def test_build_agent_instruction_includes_post_action_and_entity_type_id() -> None:
    instruction = FilehandlerServiceManager._build_agent_instruction(
        "resume.pdf",
        [{"type": "create_entity", "entity_type": "candidate", "entity_type_id": "uuid-123"}],
    )
    # The filename must NOT appear — it tempts the model to pass it as a document_id.
    assert "resume.pdf" not in instruction
    assert "read_document" in instruction
    assert "create_entity" in instruction
    assert "candidate" in instruction
    assert "uuid-123" in instruction


def test_build_agent_instruction_without_post_actions() -> None:
    instruction = FilehandlerServiceManager._build_agent_instruction("jd.txt", [])
    assert "jd.txt" not in instruction
    assert "read_document" in instruction
    assert "Post-action" not in instruction


def test_build_agent_instruction_includes_owner_entity_for_update() -> None:
    instruction = FilehandlerServiceManager._build_agent_instruction(
        "resume.pdf",
        [{"type": "update_entity", "entity_type": "candidate"}],
        owner_entity_id="ent-123",
        owner_entity_type="candidate",
    )
    assert "ent-123" in instruction
    assert "update_entity" in instruction
    # The exact entity type is named so tools like get_form_schema receive it
    # verbatim instead of a guessed synonym.
    assert "candidate" in instruction
    assert "verbatim" in instruction


def test_build_agent_instruction_omits_owner_when_absent() -> None:
    instruction = FilehandlerServiceManager._build_agent_instruction("resume.pdf", [])
    assert "attached to entity_id" not in instruction


def test_build_agent_instruction_drops_update_entity_post_action_without_owner() -> None:
    # No owner_entity_id (document-upload-driven entity creation) — an update_entity
    # post-action has nothing to update and must not be offered to the agent, or it
    # will guess an entity_id and fail (STAT-356 regression).
    instruction = FilehandlerServiceManager._build_agent_instruction(
        "resume.pdf",
        [
            {"type": "update_entity", "entity_type": "candidate"},
            {"type": "create_entity", "entity_type": "candidate", "entity_type_id": "uuid-123"},
        ],
    )
    assert "update_entity" not in instruction
    assert "create_entity" in instruction
    assert "uuid-123" in instruction


def test_build_agent_instruction_keeps_update_entity_post_action_with_owner() -> None:
    instruction = FilehandlerServiceManager._build_agent_instruction(
        "resume.pdf",
        [{"type": "update_entity", "entity_type": "candidate"}],
        owner_entity_id="ent-123",
        owner_entity_type="candidate",
    )
    assert "Post-action: update_entity" in instruction


class _FakeRun:
    def __init__(self, tool_calls: list[dict[str, object]]) -> None:
        self.metadata = {"tool_calls": tool_calls}


def test_created_entity_from_tool_calls_extracts_entity_id() -> None:
    run = _FakeRun(
        [
            {"tool": "read_document", "success": True},
            {
                "tool": "create_entity",
                "success": True,
                "result": {"output": {"entity_id": "ent-456", "entity_type_id": "type-789"}},
            },
        ]
    )
    assert FilehandlerServiceManager._created_entity_from_tool_calls(run) == {
        "entity_id": "ent-456",
        "entity_type_id": "type-789",
    }


def test_created_entity_from_tool_calls_ignores_failed_create_entity() -> None:
    run = _FakeRun(
        [
            {
                "tool": "create_entity",
                "success": False,
                "result": {"output": {"entity_id": "ent-456"}},
            },
        ]
    )
    assert FilehandlerServiceManager._created_entity_from_tool_calls(run) is None


def test_created_entity_from_tool_calls_ignores_update_entity() -> None:
    run = _FakeRun(
        [
            {
                "tool": "update_entity",
                "success": True,
                "result": {"output": {"entity_id": "ent-456"}},
            },
        ]
    )
    assert FilehandlerServiceManager._created_entity_from_tool_calls(run) is None


def test_created_entity_from_tool_calls_handles_missing_metadata() -> None:
    assert FilehandlerServiceManager._created_entity_from_tool_calls(object()) is None


def test_active_processing_count_starts_at_zero() -> None:
    from filehandler.db_models import FilehandlerModelService

    mgr = FilehandlerServiceManager(FilehandlerModelService(database_service_manager=None), None, None)
    assert mgr.active_processing_count() == 0


# --- _run_agent_processing_inner status-decision tests (STAT: false-FAILED fix) ---
#
# These exercise the real method end to end (not just a helper), with the agent and DB
# layers faked, so they prove the actual regression scenario from the RCA: a tool call
# that failed then succeeded on retry, in a run that otherwise completed, must land on
# PROCESSED — not FAILED. Run status is the only input to the decision now.




class _FakeAgentRun:
    def __init__(
        self,
        status: str,
        tool_calls: list[dict[str, object]] | None = None,
        error: str | None = None,
        run_id: str = "run-1",
    ) -> None:
        self.run_id = run_id
        self.status = status
        self.error = error
        self.metadata = {"tool_calls": tool_calls or []}


class _RecordingDbModelService:
    """Records every status/metadata write `_run_agent_processing_inner` makes."""

    def __init__(self) -> None:
        self.status_calls: list[dict[str, object]] = []
        self.metadata_calls: list[dict[str, object]] = []

    def set_file_status(
        self, organization_id: str, file_id: str, status: str, failure_reason: str | None = None
    ) -> None:
        self.status_calls.append(
            {
                "organization_id": organization_id,
                "file_id": file_id,
                "status": status,
                "failure_reason": failure_reason,
            }
        )

    def merge_file_metadata(self, organization_id: str, file_id: str, metadata: dict[str, object]) -> None:
        self.metadata_calls.append(metadata)

    def set_file_owner(self, organization_id: str, file_id: str, owner_entity_id: str) -> None:
        pass


class _StubAgentServiceManager:
    def __init__(self, run: object) -> None:
        self._run = run

    def run_agent_for_actor(self, actor: dict[str, object], request: object) -> object:
        return self._run


def _make_manager(run: object) -> tuple[FilehandlerServiceManager, _RecordingDbModelService]:
    db = _RecordingDbModelService()
    mgr = FilehandlerServiceManager(db, None, None)
    mgr.agent_service_manager = _StubAgentServiceManager(run)
    mgr.notifications_service_manager = None
    return mgr, db


def test_run_agent_processing_inner_completed_with_retried_tool_call_is_processed() -> None:
    # The exact false-FAILED regression: create_entity fails once, then succeeds on retry,
    # inside a run that completed. Must be PROCESSED, not FAILED.
    run = _FakeAgentRun(
        status="completed",
        tool_calls=[
            {"tool": "create_entity", "success": False},
            {"tool": "create_entity", "success": True, "result": {"output": {"entity_id": "e1"}}},
        ],
    )
    mgr, db = _make_manager(run)

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert [c["status"] for c in db.status_calls] == [FileRecordStatus.PROCESSED.value]


def test_run_agent_processing_inner_completed_with_tool_that_never_succeeds_is_processed() -> None:
    # Per the agreed scope boundary: a tool that fails on every attempt no longer matters —
    # only run.status does. Completed run => PROCESSED even though nothing ever succeeded.
    run = _FakeAgentRun(
        status="completed",
        tool_calls=[
            {"tool": "update_entity", "success": False},
            {"tool": "update_entity", "success": False},
        ],
    )
    mgr, db = _make_manager(run)

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert [c["status"] for c in db.status_calls] == [FileRecordStatus.PROCESSED.value]


def test_run_agent_processing_inner_completed_with_zero_tool_calls_is_processed() -> None:
    # Agreed, intentional behavior — a completed run that never called any tool still
    # counts as PROCESSED; this must not silently start requiring a tool call to have run.
    run = _FakeAgentRun(status="completed", tool_calls=[])
    mgr, db = _make_manager(run)

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert [c["status"] for c in db.status_calls] == [FileRecordStatus.PROCESSED.value]


def test_run_agent_processing_inner_failed_status_sets_failed_with_run_error() -> None:
    run = _FakeAgentRun(status="failed", error="SDK crash: connection reset")
    mgr, db = _make_manager(run)

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert len(db.status_calls) == 1
    call = db.status_calls[0]
    assert call["status"] == FileRecordStatus.FAILED.value
    assert call["failure_reason"] == "SDK crash: connection reset"


def test_run_agent_processing_inner_failed_status_without_run_error_falls_back_to_status_message() -> None:
    run = _FakeAgentRun(status="failed", error=None)
    mgr, db = _make_manager(run)

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert db.status_calls[0]["status"] == FileRecordStatus.FAILED.value
    assert db.status_calls[0]["failure_reason"] == "agent run status: failed"


def test_run_agent_processing_inner_waiting_for_approval_status_sets_failed() -> None:
    # Documented, unchanged edge case (see spec's Open Decisions): any non-"completed"
    # status — including "waiting_for_approval" — still falls into the FAILED branch today.
    run = _FakeAgentRun(status="waiting_for_approval", error=None)
    mgr, db = _make_manager(run)

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert db.status_calls[0]["status"] == FileRecordStatus.FAILED.value
    assert db.status_calls[0]["failure_reason"] == "agent run status: waiting_for_approval"


def test_run_agent_processing_inner_raises_before_run_returned_sets_failed_with_exception() -> None:
    class _RaisingAgentServiceManager:
        def run_agent_for_actor(self, actor: dict[str, object], request: object) -> object:
            raise RuntimeError("agent dispatch exploded")

    db = _RecordingDbModelService()
    mgr = FilehandlerServiceManager(db, None, None)
    mgr.agent_service_manager = _RaisingAgentServiceManager()
    mgr.notifications_service_manager = None

    mgr._run_agent_processing_inner("org-1", "user-1", "file-1", "resume.pdf", "agent-1", [])

    assert db.status_calls[0]["status"] == FileRecordStatus.FAILED.value
    assert db.status_calls[0]["failure_reason"] == "agent dispatch exploded"
