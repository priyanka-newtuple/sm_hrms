"""Version-one task template copied from the legacy default onboarding flow.

The case pins this version. Future edits should add a new version rather than
change these steps for in-flight hires.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(frozen=True)
class OnboardingStep:
    sequence: int
    key: str
    title: str
    assignee_role: str | None
    # Days after the joining date the step is due; 0 means ready by day one (pre-boarding).
    due_after_joining: int
    depends_on: tuple[int, ...] = ()

    def due_date(self, joining: date, today: date) -> datetime:
        """Due relative to the joining date, or to today for a hire added after they joined.
        Midday UTC keeps the calendar day the same across Newtuple's time zones."""
        return datetime.combine(max(joining, today) + timedelta(days=self.due_after_joining), time(12), tzinfo=UTC)


DEFAULT_ONBOARDING_STEPS = (
    OnboardingStep(
        1, "newtuple_id", "Create Newtuple ID (Google Workspace account)", "hrms_office_admin", 0
    ),
    OnboardingStep(2, "razorpay_account", "Create Razorpay payroll account", "hrms_finance", 0),
    OnboardingStep(3, "hrms_invitation", "Invite employee to HRMS", "hrms_hr_full", 0, (1,)),
    OnboardingStep(4, "employee_profile", "Employee fills personal & bank details", None, 3, (3,)),
    OnboardingStep(5, "documents", "Upload documents & experience certificates", None, 3, (3,)),
    OnboardingStep(
        6, "asset_allocation", "Allocate laptop and access badge", "hrms_office_admin", 0, (1,)
    ),
    OnboardingStep(7, "hr_orientation", "HR orientation session", "hrms_hr_basic", 5, (4,)),
    OnboardingStep(
        8,
        "pm_allocation",
        "Allocate to project & project manager",
        "hrms_delivery_manager",
        7,
        (4,),
    ),
)
