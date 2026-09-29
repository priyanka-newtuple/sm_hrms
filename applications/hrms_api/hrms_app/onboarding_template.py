"""Version-one task template copied from the legacy default onboarding flow.

The case pins this version. Future edits should add a new version rather than
change these steps for in-flight hires.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OnboardingStep:
    sequence: int
    key: str
    title: str
    assignee_role: str | None
    due_days: int
    depends_on: tuple[int, ...] = ()


DEFAULT_ONBOARDING_STEPS = (
    OnboardingStep(
        1, "newtuple_id", "Create Newtuple ID (Google Workspace account)", "hrms_office_admin", 2
    ),
    OnboardingStep(2, "razorpay_account", "Create Razorpay payroll account", "hrms_finance", 3),
    OnboardingStep(3, "hrms_invitation", "Invite employee to HRMS", "hrms_hr_full", 3, (1,)),
    OnboardingStep(4, "employee_profile", "Employee fills personal & bank details", None, 6, (3,)),
    OnboardingStep(5, "documents", "Upload documents & experience certificates", None, 8, (3,)),
    OnboardingStep(
        6, "asset_allocation", "Allocate laptop and access badge", "hrms_office_admin", 8, (1,)
    ),
    OnboardingStep(7, "hr_orientation", "HR orientation session", "hrms_hr_basic", 10, (4,)),
    OnboardingStep(
        8,
        "pm_allocation",
        "Allocate to project & project manager",
        "hrms_delivery_manager",
        12,
        (4,),
    ),
)
