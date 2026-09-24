"""Interface models and contracts for background_jobs."""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from common.data_model import BaseModel as PydanticBaseModel
from common.data_model import ExtendedStrEnum


class ActionRunStatus(ExtendedStrEnum):
    """Lifecycle of one `action_runs` row.

    Declared here because this module owns the table. Other modules both write and query these
    values — the workflow engine creates and cancels runs, and the dashboard counts them — so
    the vocabulary belongs in one place rather than being repeated as strings.
    """

    PENDING = "pending"
    RUNNING = "running"
    PENDING_EXTERNAL = "pending_external"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionRunIdempotencyKey:
    """Builders for `action_runs.idempotency_key`.

    Declared here for the same reason as `ActionRunStatus`: this module owns the table, and the
    keys are written by the workflow engine, extended by this module's chain worker, and
    prefix-matched when deciding whether a state already has work in flight.

    The shape is a contract, not a label. Three of the four keys begin with
    `entity_state_prefix(...)`, and `has_in_flight_state_action_run` finds them by matching that
    prefix — so a key that stopped starting with `{entity_id}:{state}:` would not fail loudly,
    it would quietly stop being found and the duplicate guard would let a second action through.
    Everything is built from the one prefix method here so the two cannot drift apart.

    The SLA key deliberately does *not* use the prefix: excluding breach signals from that
    in-flight match is what lets a deadline signal sit pending while the state's own action runs.
    """

    SLA_PREFIX = "sla"

    @staticmethod
    def entity_state_prefix(entity_id: str, state: str) -> str:
        """The `{entity_id}:{state}:` prefix shared by every key scoped to one entity state."""
        return f"{entity_id}:{state}:"

    @classmethod
    def state_entry(
        cls,
        *,
        entity_id: str,
        state: str,
        transition_key: str,
        state_version: int,
        action_index: int = 0,
    ) -> str:
        """First action scheduled on arriving in a state, keyed to that arrival's version."""
        prefix = cls.entity_state_prefix(entity_id, state)
        return f"{prefix}{transition_key}:v{state_version}:a{action_index}"

    @classmethod
    def chain_continuation(
        cls, *, entity_id: str, state: str, chain_id: str, action_index: int
    ) -> str:
        """Each subsequent action in a chain, created by the worker as the previous one ends."""
        prefix = cls.entity_state_prefix(entity_id, state)
        return f"{prefix}chain:{chain_id}:a{action_index}"

    @classmethod
    def manual_rerun(cls, *, entity_id: str, state: str, run_id: str) -> str:
        """A rerun a user asked for; keyed on the new run so it is a fresh attempt, not a dedupe."""
        prefix = cls.entity_state_prefix(entity_id, state)
        return f"{prefix}rerun:{run_id}"

    @classmethod
    def sla_breach_signal(cls, *, entity_id: str, state: str, entered_at_epoch: int) -> str:
        """The breach signal for one arrival in a state, keyed on when that arrival happened."""
        return f"{cls.SLA_PREFIX}:{entity_id}:{state}:{entered_at_epoch}"


class IntakeJobContract(PydanticBaseModel):
    """Normalized interface contract for an intake job."""

    job_id: str = Field(..., min_length=1, description="Intake job identifier")
    organization_id: str = Field(..., min_length=1, description="Organization identifier")
    status: str = Field(..., min_length=1, description="Job processing state")
    source_type: str = Field(..., min_length=1, description="Source type label")
    file_count: int = Field(..., ge=0, description="Total number of source files")
    processed_count: int = Field(default=0, ge=0, description="Number of processed files")
    failed_count: int = Field(default=0, ge=0, description="Number of failed files")
    subject_entity_type: str | None = Field(default=None, description="Target entity type")
    created_at: str | None = Field(default=None, description="Creation timestamp")
    updated_at: str | None = Field(default=None, description="Update timestamp")
    context: dict[str, object] = Field(default_factory=dict, description="Contextual payload")


class IntakeReadPort(Protocol):
    """Read contract consumed by dependent managers."""

    def get_job(self, organization_id: str, job_id: str) -> IntakeJobContract | None:
        """Return a single intake job."""
