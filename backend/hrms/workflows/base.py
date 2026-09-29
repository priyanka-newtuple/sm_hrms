from __future__ import annotations

from abc import ABC, abstractmethod

from hrms.models.enums import OnboardingStatus, OnboardingType
from hrms.models.onboarding import OnboardingRecord


class WorkflowProvider(ABC):
    """
    Abstraction over "who actually drives this approval/onboarding workflow".
    Lets NativeWorkflowProvider (simple in-app state machine) and
    FlowtupleWorkflowProvider (embeds the separately-deployed Flowtuple system)
    be swapped without touching callers — the onboarding API always talks to
    a WorkflowProvider, never to Flowtuple specifics directly.
    """

    @abstractmethod
    async def start(self, record: OnboardingRecord, workflow_type: OnboardingType) -> None: ...

    @abstractmethod
    def embed_url(self, record: OnboardingRecord) -> str | None:
        """URL for the frontend to render in an <iframe>, or None if not applicable."""
        ...

    @abstractmethod
    def status(self, record: OnboardingRecord) -> OnboardingStatus: ...
