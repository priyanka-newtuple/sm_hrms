"""
Vocabulary of the authorization engine, taken verbatim from the
"Permission Definitions" sheet of HRMS_Roles_Permissions_Access_Control.xlsx.

Every grant is a tuple of three independent dimensions — Action, RecordScope,
DataProfile — never a single flag. See app/authz/engine.py for how these are
evaluated and app/seed/permission_matrix.py for the source data.
"""

from enum import Enum


class Action(str, Enum):
    NONE = "none"
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    COMPLETE = "complete"
    SUBMIT = "submit"
    MANAGE = "manage"  # View + Create + Edit. Does NOT imply Approve or Delete.
    APPROVE = "approve"
    DELETE = "delete"  # Always audit-logged.
    FULL = "full"  # All actions, including admin/config. Always audit-logged.


# Actions implied by a broader grant. MANAGE expands to VIEW/CREATE/EDIT;
# FULL expands to everything. APPROVE, DELETE and COMPLETE are never implied
# by MANAGE — they must be granted explicitly, per the spec.
_ACTION_IMPLICATIONS: dict[Action, frozenset[Action]] = {
    Action.MANAGE: frozenset({Action.VIEW, Action.CREATE, Action.EDIT, Action.MANAGE}),
    Action.FULL: frozenset(a for a in Action if a != Action.NONE),
}


def expand_actions(granted: list[Action]) -> frozenset[Action]:
    """Expand a role's granted action list into the full set of actions it permits."""
    result: set[Action] = set()
    for action in granted:
        result |= _ACTION_IMPLICATIONS.get(action, frozenset({action}))
    return frozenset(result)


class RecordScope(str, Enum):
    NONE = "none"  # No records at all (feature not accessible).
    SELF = "self"
    ASSIGNED = "assigned"
    PROJECT_TEAM = "project_team"
    TEAM = "team"
    ALL = "all"


# Ordering used only for "does scope A cover at least scope B" comparisons in tests/UI.
_SCOPE_ORDER = [
    RecordScope.NONE,
    RecordScope.SELF,
    RecordScope.ASSIGNED,
    RecordScope.PROJECT_TEAM,
    RecordScope.TEAM,
    RecordScope.ALL,
]


def scope_at_least(scope: RecordScope, minimum: RecordScope) -> bool:
    return _SCOPE_ORDER.index(scope) >= _SCOPE_ORDER.index(minimum)


class DataProfile(str, Enum):
    NONE = "none"
    BASIC = "basic"
    LIMITED = "limited"
    NON_SENSITIVE = "non_sensitive"
    COMMERCIAL = "commercial"
    ALL = "all"


class FeatureKey(str, Enum):
    EMPLOYEE_DIRECTORY = "employee_directory"
    EMPLOYEE_ONBOARDING = "employee_onboarding"
    EMPLOYEE_OFFBOARDING = "employee_offboarding"
    CUSTOMERS = "customers"
    PROJECTS = "projects"
    ALLOCATIONS = "allocations"
    TIMESHEETS = "timesheets"
    ASSET_MANAGEMENT = "asset_management"
    EXPENSE_MANAGEMENT = "expense_management"
    HELP_DESK = "help_desk"
    PERFORMANCE_MANAGEMENT = "performance_management"
    HR_COCKPIT = "hr_cockpit"


class PermissionKey(str, Enum):
    """Granular sensitive-field flags from the "Permission Keys" sheet."""

    VIEW_EMPLOYEE_COMPENSATION = "view_employee_compensation"
    VIEW_EMPLOYEE_COST = "view_employee_cost"
    VIEW_BILLING_RATE = "view_billing_rate"
    VIEW_CUSTOMER_CONTRACT_VALUE = "view_customer_contract_value"
    VIEW_PROJECT_REVENUE = "view_project_revenue"
    VIEW_PROJECT_MARGIN = "view_project_margin"
    VIEW_INVOICES = "view_invoices"
    VIEW_BANK_PAYROLL_DATA = "view_bank_payroll_data"


class RoleName(str, Enum):
    SUPER_ADMIN = "Super Admin"
    EMPLOYEE = "Employee"
    HR_BASIC = "HR - Basic"
    HR_FULL = "HR - Full"
    PROJECT_MANAGER = "Project Manager"
    DELIVERY_MANAGER = "Delivery Manager"
    FINANCE = "Finance"
    OFFICE_ADMIN = "Office Admin"
    RECRUITER = "Recruiter"
