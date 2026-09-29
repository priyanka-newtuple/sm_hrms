from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import object_session
from sqlalchemy.orm.attributes import set_committed_value

from hrms.models.enums import OnboardingStatus, OnboardingType
from hrms.models.onboarding import OnboardingRecord
from hrms.workflows.base import WorkflowProvider

DEFAULT_ONBOARDING_TASKS = [
    "Collect signed offer letter",
    "Issue laptop and access badge",
    "Provision email and internal accounts",
    "HR orientation session",
    "Assign reporting manager and buddy",
]

DEFAULT_OFFBOARDING_TASKS = [
    "Return company assets",
    "Revoke system access",
    "Full and final settlement",
    "Exit interview",
]


class NativeWorkflowProvider(WorkflowProvider):
    """Simple in-app checklist-driven workflow, used when Flowtuple isn't configured."""

    async def start(self, record: OnboardingRecord, workflow_type: OnboardingType) -> None:
        from hrms.models.onboarding import OnboardingTask

        record.status = OnboardingStatus.IN_PROGRESS
        record.started_at = datetime.now(UTC)
        titles = DEFAULT_ONBOARDING_TASKS if workflow_type == OnboardingType.ONBOARDING else DEFAULT_OFFBOARDING_TASKS
        tasks = [OnboardingTask(onboarding_record_id=record.id, title=t, seq=i + 1) for i, t in enumerate(titles)]
        session = object_session(record)
        for task in tasks:
            session.add(task)
        set_committed_value(record, "tasks", tasks)

    def embed_url(self, record: OnboardingRecord) -> str | None:
        return None

    def status(self, record: OnboardingRecord) -> OnboardingStatus:
        return record.status
