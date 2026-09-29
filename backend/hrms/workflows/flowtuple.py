from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode

from hrms.config import get_settings
from hrms.models.enums import OnboardingStatus, OnboardingType
from hrms.models.onboarding import OnboardingRecord
from hrms.workflows.base import WorkflowProvider

settings = get_settings()


class FlowtupleWorkflowProvider(WorkflowProvider):
    """
    Embeds the separately-deployed Flowtuple workflow system via iframe.
    This is a placeholder integration: it builds a deep-link URL from
    FLOWTUPLE_BASE_URL + employee/workflow context and stores an opaque
    workflow id. It does not yet call a real Flowtuple API for status —
    swap the `status()` method for a real call once Flowtuple exposes one,
    without needing to change any caller of WorkflowProvider.
    """

    async def start(self, record: OnboardingRecord, workflow_type: OnboardingType) -> None:
        record.status = OnboardingStatus.IN_PROGRESS
        record.started_at = datetime.now(UTC)
        record.flowtuple_workflow_id = f"{workflow_type.value}-{record.employee_id}"

    def embed_url(self, record: OnboardingRecord) -> str | None:
        if not record.flowtuple_workflow_id:
            return None
        params = {
            "employeeId": str(record.employee_id),
            "workflowId": record.flowtuple_workflow_id,
            "returnUrl": settings.FRONTEND_URL,
        }
        return f"{settings.FLOWTUPLE_BASE_URL.rstrip('/')}/embed?{urlencode(params)}"

    def status(self, record: OnboardingRecord) -> OnboardingStatus:
        # Placeholder: real integration would poll/receive a webhook from Flowtuple.
        return record.status


def get_workflow_provider() -> WorkflowProvider:
    from hrms.workflows.native import NativeWorkflowProvider

    return FlowtupleWorkflowProvider() if settings.FLOWTUPLE_ENABLED else NativeWorkflowProvider()
