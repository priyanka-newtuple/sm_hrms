"""Onboarding task templates. Version one was copied from the legacy default flow.

Each case pins the version it started on. Edits add a new version rather than
change the steps of in-flight hires.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(frozen=True)
class OnboardingStep:
    sequence: int
    key: str
    title: str
    assignee_role: str | None  # None: the new hire; REPORTING_MANAGER: the hire's own manager
    # Days after the joining date the step is due; 0 means ready by day one (pre-boarding).
    due_after_joining: int
    depends_on: tuple[int, ...] = ()

    def due_date(self, joining: date, today: date) -> datetime:
        """Due relative to the joining date, or to today for a hire added after they joined.
        Midday UTC keeps the calendar day the same across Newtuple's time zones."""
        return datetime.combine(max(joining, today) + timedelta(days=self.due_after_joining), time(12), tzinfo=UTC)


REPORTING_MANAGER = "reporting_manager"

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

# Version two adds the step every hire's own manager owns.
MANAGER_WELCOME = OnboardingStep(
    9, "manager_welcome", "Manager welcome and first-week plan", REPORTING_MANAGER, 0, (3,)
)
TEMPLATES = {1: DEFAULT_ONBOARDING_STEPS, 2: (*DEFAULT_ONBOARDING_STEPS, MANAGER_WELCOME)}
CURRENT_TEMPLATE_VERSION = 2
