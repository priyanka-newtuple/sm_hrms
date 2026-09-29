"""Plain domain enums (workflow/status values) — distinct from app/authz/enums.py,
which defines the permission model vocabulary."""

from enum import Enum


class EmploymentStatus(str, Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    OFFBOARDING = "offboarding"
    OFFBOARDED = "offboarded"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    CONTRACT = "contract"
    INTERN = "intern"


class ExitType(str, Enum):
    RESIGNATION = "resignation"
    TERMINATION = "termination"
    END_OF_CONTRACT = "end_of_contract"
    RETIREMENT = "retirement"


class CustomerStatus(str, Enum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    ARCHIVED = "archived"


class ProjectStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# Statuses that still consume delivery capacity / block a customer from being archived.
OPEN_PROJECT_STATUSES = (ProjectStatus.PLANNED, ProjectStatus.ACTIVE, ProjectStatus.ON_HOLD)
# Statuses a new allocation may be attached to.
ALLOCATABLE_PROJECT_STATUSES = (ProjectStatus.PLANNED, ProjectStatus.ACTIVE)


class EngagementType(str, Enum):
    TIME_AND_MATERIALS = "time_and_materials"
    FIXED_BID = "fixed_bid"
    RETAINER = "retainer"


class ProjectHealth(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class AllocationStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Allocations that count toward an employee's committed capacity.
COMMITTED_ALLOCATION_STATUSES = (AllocationStatus.PLANNED, AllocationStatus.ACTIVE)


class TimesheetStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class AssetStatus(str, Enum):
    IN_STOCK = "in_stock"
    ASSIGNED = "assigned"
    UNDER_REPAIR = "under_repair"
    RETIRED = "retired"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class OnboardingStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class OnboardingType(str, Enum):
    ONBOARDING = "onboarding"
    OFFBOARDING = "offboarding"


class TaskStatus(str, Enum):
    """Lifecycle of one onboarding step. PENDING = blocked on dependencies;
    READY = actionable now (this is when the assignee gets emailed)."""

    PENDING = "pending"
    READY = "ready"
    DONE = "done"
    SKIPPED = "skipped"


# Statuses that count as "finished" for dependency resolution / record completion.
TERMINAL_TASK_STATUSES = (TaskStatus.DONE, TaskStatus.SKIPPED)


class AssigneeRule(str, Enum):
    """How a template step resolves to a concrete person when onboarding starts."""

    ROLE = "role"  # first active employee holding assignee_role
    NEW_HIRE = "new_hire"  # the employee being onboarded
    REPORTING_MANAGER = "reporting_manager"  # the new hire's manager


class TaskActionType(str, Enum):
    """What completes a step. MANUAL = a person confirms; the others are
    auto-completed by real records landing in their own modules."""

    MANUAL = "manual"
    INVITE_EMPLOYEE = "invite_employee"  # system sends HRMS invitation, auto-completes
    EMPLOYEE_PROFILE = "employee_profile"  # new hire submits the self-service wizard
    DOCUMENT_COLLECTION = "document_collection"  # all required docs verified by HR
    ASSET_ASSIGNMENT = "asset_assignment"  # an asset_assignments row is created
    PROJECT_ALLOCATION = "project_allocation"  # an allocations row is created


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class DocumentType(str, Enum):
    ID_PROOF = "id_proof"
    ADDRESS_PROOF = "address_proof"
    PAN = "pan"
    EDUCATION_CERTIFICATE = "education_certificate"
    EXPERIENCE_CERTIFICATE = "experience_certificate"
    SIGNED_OFFER_LETTER = "signed_offer_letter"
    OTHER = "other"


# Doc types every new hire must have verified before the document-collection
# step auto-completes. Experience certificates are collected but not required
# (freshers won't have one) — HR can still verify or reject them.
REQUIRED_DOCUMENT_TYPES = (
    DocumentType.ID_PROOF,
    DocumentType.PAN,
    DocumentType.EDUCATION_CERTIFICATE,
    DocumentType.SIGNED_OFFER_LETTER,
)


class DocumentStatus(str, Enum):
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"


class OutboxStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
