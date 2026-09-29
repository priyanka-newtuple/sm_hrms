"""
Import every model module here so Alembic's autogenerate and Base.metadata
see the full schema regardless of which module happens to import `Base` first.
"""

from hrms.models.allocation import Allocation
from hrms.models.asset import Asset, AssetAssignment
from hrms.models.audit import AuditLog
from hrms.models.document import EmployeeDocument
from hrms.models.employee import Employee
from hrms.models.helpdesk import HelpdeskCategory, HelpdeskTicket
from hrms.models.hr_content import EmployeeReferral, JobDescription, JobOpening, LearningEvent, OrganizationPolicy
from hrms.models.invitation import EmployeeInvitation
from hrms.models.notification import NotificationOutbox
from hrms.models.onboarding import OnboardingRecord, OnboardingTask
from hrms.models.onboarding_template import OnboardingTemplate, OnboardingTemplateStep
from hrms.models.performance import PerformanceCycle, PerformanceGoal, PerformanceReview, ProjectFeedback
from hrms.models.project import Customer, Project, ProjectApprovalRequest
from hrms.models.reference_data import Department, Designation, ProjectRole
from hrms.models.role import Role, RoleFeaturePermission, RolePermissionKey
from hrms.models.timesheet import Holiday, LeaveRequest, Timesheet, TimesheetApproval
from hrms.models.user import User

__all__ = [
    "Allocation",
    "Asset",
    "AssetAssignment",
    "AuditLog",
    "Employee",
    "EmployeeDocument",
    "EmployeeInvitation",
    "HelpdeskCategory",
    "HelpdeskTicket",
    "OrganizationPolicy",
    "LearningEvent",
    "JobDescription",
    "JobOpening",
    "EmployeeReferral",
    "NotificationOutbox",
    "OnboardingRecord",
    "OnboardingTask",
    "OnboardingTemplate",
    "OnboardingTemplateStep",
    "PerformanceCycle",
    "PerformanceGoal",
    "PerformanceReview",
    "ProjectFeedback",
    "Customer",
    "Project",
    "ProjectApprovalRequest",
    "Department",
    "Designation",
    "ProjectRole",
    "Role",
    "RoleFeaturePermission",
    "RolePermissionKey",
    "Timesheet",
    "TimesheetApproval",
    "Holiday",
    "LeaveRequest",
    "User",
]
