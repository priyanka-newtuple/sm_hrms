"""
Baseline translation of HRMS_Roles_Permissions_Access_Control.xlsx into the
Action / RecordScope / DataProfile model, using the workbook's own
"Permission Mapping" sheet to resolve each shorthand cell in "Feature
Permissions", and the "Permission Keys" sheet's "Recommended Roles" column
for the granular sensitive-field grants.

Workflow ownership overrides the original workbook: only HR and Super Admin
have onboarding/offboarding module access. Other participants use assigned work.

Where a matrix cell was ambiguous in RecordScope terms (e.g. "View - Basic",
which the Permission Mapping sheet itself flags as needing an explicit
scope), the mapping sheet's own suggested resolution is used and noted
inline. Two documented simplifications, called out where they occur:
  1. Category-scoped Help Desk grants ("Manage - HR/Admin", "Manage - Finance",
     "Manage - Admin/Facilities") are modeled as RecordScope.ALL — ticket
     *category* filtering isn't one of the five RecordScope values, so it's
     left as a service-layer concern rather than forced into this model.
  2. "View - Approved" for Finance on Timesheets is modeled as RecordScope.ALL
     with a status filter applied in the timesheet service, for the same
     reason — "Approved" is a status, not a record scope.
"""

from hrms.authz.enums import Action, DataProfile, FeatureKey, PermissionKey, RecordScope, RoleName

A = Action
S = RecordScope
D = DataProfile
F = FeatureKey

# role -> feature -> (actions, scope, data_profile)
FEATURE_PERMISSIONS: dict[RoleName, dict[FeatureKey, tuple[list[Action], RecordScope, DataProfile]]] = {
    RoleName.SUPER_ADMIN: {
        F.EMPLOYEE_DIRECTORY: ([A.FULL], S.ALL, D.ALL),
        F.EMPLOYEE_ONBOARDING: ([A.FULL], S.ALL, D.ALL),
        F.EMPLOYEE_OFFBOARDING: ([A.FULL], S.ALL, D.ALL),
        F.CUSTOMERS: ([A.FULL], S.ALL, D.ALL),
        F.PROJECTS: ([A.FULL], S.ALL, D.ALL),
        F.ALLOCATIONS: ([A.FULL], S.ALL, D.ALL),
        F.TIMESHEETS: ([A.FULL], S.ALL, D.ALL),
        F.ASSET_MANAGEMENT: ([A.FULL], S.ALL, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.FULL], S.ALL, D.ALL),
        F.HELP_DESK: ([A.FULL], S.ALL, D.ALL),
        F.PERFORMANCE_MANAGEMENT: ([A.FULL], S.ALL, D.ALL),
        F.HR_COCKPIT: ([A.FULL], S.ALL, D.ALL),
    },
    RoleName.EMPLOYEE: {
        F.EMPLOYEE_DIRECTORY: ([A.VIEW, A.EDIT], S.SELF, D.ALL),
        F.EMPLOYEE_ONBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.EMPLOYEE_OFFBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.CUSTOMERS: ([A.NONE], S.NONE, D.NONE),
        F.PROJECTS: ([A.VIEW], S.ASSIGNED, D.ALL),
        F.ALLOCATIONS: ([A.VIEW], S.SELF, D.ALL),
        F.TIMESHEETS: ([A.VIEW, A.CREATE, A.EDIT], S.SELF, D.ALL),
        F.ASSET_MANAGEMENT: ([A.VIEW], S.SELF, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.VIEW, A.CREATE], S.SELF, D.ALL),
        F.HELP_DESK: ([A.VIEW, A.CREATE], S.SELF, D.ALL),
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT, A.SUBMIT], S.SELF, D.ALL),
        F.HR_COCKPIT: ([A.NONE], S.NONE, D.NONE),
    },
    RoleName.HR_BASIC: {
        F.EMPLOYEE_DIRECTORY: ([A.VIEW, A.CREATE, A.EDIT], S.ALL, D.NON_SENSITIVE),
        F.EMPLOYEE_ONBOARDING: ([A.MANAGE], S.ALL, D.ALL),
        F.EMPLOYEE_OFFBOARDING: ([A.MANAGE], S.ALL, D.ALL),
        F.CUSTOMERS: ([A.NONE], S.NONE, D.NONE),
        F.PROJECTS: ([A.VIEW], S.ALL, D.ALL),
        F.ALLOCATIONS: ([A.VIEW], S.ALL, D.ALL),
        F.TIMESHEETS: ([A.VIEW], S.ALL, D.ALL),
        F.ASSET_MANAGEMENT: ([A.MANAGE], S.ALL, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.VIEW], S.ALL, D.ALL),
        F.HELP_DESK: ([A.MANAGE], S.ALL, D.ALL),  # category scope simplification (see module docstring)
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW], S.ALL, D.NON_SENSITIVE),
        F.HR_COCKPIT: ([A.MANAGE, A.SUBMIT], S.ALL, D.ALL),
    },
    RoleName.HR_FULL: {
        F.EMPLOYEE_DIRECTORY: ([A.MANAGE], S.ALL, D.ALL),
        F.EMPLOYEE_ONBOARDING: ([A.MANAGE], S.ALL, D.ALL),
        F.EMPLOYEE_OFFBOARDING: ([A.MANAGE], S.ALL, D.ALL),
        F.CUSTOMERS: ([A.VIEW], S.ALL, D.ALL),
        F.PROJECTS: ([A.VIEW], S.ALL, D.ALL),
        F.ALLOCATIONS: ([A.VIEW], S.ALL, D.ALL),
        F.TIMESHEETS: ([A.VIEW, A.APPROVE], S.ALL, D.ALL),
        F.ASSET_MANAGEMENT: ([A.MANAGE], S.ALL, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.VIEW], S.ALL, D.ALL),
        F.HELP_DESK: ([A.MANAGE], S.ALL, D.ALL),
        F.PERFORMANCE_MANAGEMENT: ([A.MANAGE, A.APPROVE], S.ALL, D.ALL),
        F.HR_COCKPIT: ([A.MANAGE, A.SUBMIT, A.APPROVE], S.ALL, D.ALL),
    },
    RoleName.PROJECT_MANAGER: {
        # "View - Basic" resolved per Permission Mapping sheet -> "View - Project Team - Basic"
        F.EMPLOYEE_DIRECTORY: ([A.VIEW], S.PROJECT_TEAM, D.BASIC),
        F.EMPLOYEE_ONBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.EMPLOYEE_OFFBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.CUSTOMERS: ([A.VIEW], S.ASSIGNED, D.ALL),
        F.PROJECTS: ([A.MANAGE, A.SUBMIT], S.ASSIGNED, D.ALL),
        F.ALLOCATIONS: ([A.MANAGE], S.ASSIGNED, D.ALL),
        F.TIMESHEETS: ([A.VIEW, A.APPROVE], S.ASSIGNED, D.ALL),
        F.ASSET_MANAGEMENT: ([A.VIEW], S.PROJECT_TEAM, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.VIEW, A.APPROVE], S.ASSIGNED, D.ALL),
        F.HELP_DESK: ([A.VIEW, A.CREATE], S.ASSIGNED, D.ALL),
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT, A.SUBMIT, A.APPROVE], S.TEAM, D.ALL),
        F.HR_COCKPIT: ([A.NONE], S.NONE, D.NONE),
    },
    RoleName.DELIVERY_MANAGER: {
        F.EMPLOYEE_DIRECTORY: ([A.VIEW], S.ALL, D.BASIC),
        F.EMPLOYEE_ONBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.EMPLOYEE_OFFBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.CUSTOMERS: ([A.VIEW], S.ALL, D.ALL),
        F.PROJECTS: ([A.MANAGE, A.SUBMIT], S.ALL, D.ALL),
        F.ALLOCATIONS: ([A.MANAGE], S.ALL, D.ALL),
        F.TIMESHEETS: ([A.VIEW, A.APPROVE], S.ALL, D.ALL),
        F.ASSET_MANAGEMENT: ([A.VIEW], S.ALL, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.VIEW, A.APPROVE], S.ALL, D.ALL),
        F.HELP_DESK: ([A.VIEW], S.ALL, D.ALL),
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT, A.SUBMIT, A.APPROVE], S.TEAM, D.ALL),
        F.HR_COCKPIT: ([A.NONE], S.NONE, D.NONE),
    },
    RoleName.FINANCE: {
        F.EMPLOYEE_DIRECTORY: ([A.VIEW], S.ALL, D.LIMITED),
        F.EMPLOYEE_ONBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.EMPLOYEE_OFFBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.CUSTOMERS: ([A.MANAGE], S.ALL, D.COMMERCIAL),
        F.PROJECTS: ([A.VIEW], S.ALL, D.ALL),
        F.ALLOCATIONS: ([A.VIEW], S.ALL, D.ALL),
        # "View - Approved" -> status filter applied in service layer (see module docstring)
        F.TIMESHEETS: ([A.VIEW], S.ALL, D.ALL),
        F.ASSET_MANAGEMENT: ([A.VIEW], S.ALL, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.MANAGE], S.ALL, D.ALL),
        F.HELP_DESK: ([A.MANAGE], S.ALL, D.ALL),  # category scope simplification
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT, A.SUBMIT], S.SELF, D.ALL),
        F.HR_COCKPIT: ([A.NONE], S.NONE, D.NONE),
    },
    RoleName.OFFICE_ADMIN: {
        F.EMPLOYEE_DIRECTORY: ([A.VIEW], S.ALL, D.BASIC),
        F.EMPLOYEE_ONBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.EMPLOYEE_OFFBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.CUSTOMERS: ([A.NONE], S.NONE, D.NONE),
        F.PROJECTS: ([A.VIEW], S.ALL, D.BASIC),
        F.ALLOCATIONS: ([A.VIEW], S.ALL, D.BASIC),
        F.TIMESHEETS: ([A.VIEW, A.CREATE, A.EDIT], S.SELF, D.ALL),
        F.ASSET_MANAGEMENT: ([A.MANAGE], S.ALL, D.ALL),
        # "No Approval" -> Approve intentionally excluded
        F.EXPENSE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT], S.ALL, D.ALL),
        F.HELP_DESK: ([A.MANAGE], S.ALL, D.ALL),  # category scope simplification
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT, A.SUBMIT], S.SELF, D.ALL),
        F.HR_COCKPIT: ([A.NONE], S.NONE, D.NONE),
    },
    RoleName.RECRUITER: {
        F.EMPLOYEE_DIRECTORY: ([A.VIEW], S.ALL, D.BASIC),
        F.EMPLOYEE_ONBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.EMPLOYEE_OFFBOARDING: ([A.NONE], S.NONE, D.NONE),
        F.CUSTOMERS: ([A.NONE], S.NONE, D.NONE),
        F.PROJECTS: ([A.VIEW], S.ASSIGNED, D.BASIC),
        F.ALLOCATIONS: ([A.VIEW], S.SELF, D.ALL),
        F.TIMESHEETS: ([A.VIEW, A.CREATE, A.EDIT], S.SELF, D.ALL),
        F.ASSET_MANAGEMENT: ([A.VIEW], S.SELF, D.ALL),
        F.EXPENSE_MANAGEMENT: ([A.VIEW, A.CREATE], S.SELF, D.ALL),
        F.HELP_DESK: ([A.VIEW, A.CREATE], S.SELF, D.ALL),
        F.PERFORMANCE_MANAGEMENT: ([A.VIEW, A.CREATE, A.EDIT, A.SUBMIT], S.SELF, D.ALL),
        F.HR_COCKPIT: ([A.MANAGE, A.SUBMIT, A.APPROVE], S.ALL, D.ALL),
    },
}

# role -> permission keys, from the "Permission Keys" sheet's Recommended Roles column.
# Super Admin is granted every key explicitly (its Full-action bypass doesn't imply this —
# the serializer checks permission_keys directly, so Full roles still need them listed).
_ALL_KEYS = list(PermissionKey)

ROLE_PERMISSION_KEYS: dict[RoleName, list[PermissionKey]] = {
    RoleName.SUPER_ADMIN: _ALL_KEYS,
    RoleName.EMPLOYEE: [],
    RoleName.HR_BASIC: [],
    RoleName.HR_FULL: [
        PermissionKey.VIEW_EMPLOYEE_COMPENSATION,
        PermissionKey.VIEW_BANK_PAYROLL_DATA,
    ],
    RoleName.PROJECT_MANAGER: [
        # "PM optional for assigned projects" — safe to grant since RecordScope.ASSIGNED
        # already restricts which projects/customers these fields can be seen on.
        PermissionKey.VIEW_BILLING_RATE,
        PermissionKey.VIEW_CUSTOMER_CONTRACT_VALUE,
        PermissionKey.VIEW_PROJECT_REVENUE,
        PermissionKey.VIEW_PROJECT_MARGIN,
    ],
    RoleName.DELIVERY_MANAGER: [
        PermissionKey.VIEW_EMPLOYEE_COST,
        PermissionKey.VIEW_BILLING_RATE,
        PermissionKey.VIEW_CUSTOMER_CONTRACT_VALUE,
        PermissionKey.VIEW_PROJECT_REVENUE,
        PermissionKey.VIEW_PROJECT_MARGIN,
        PermissionKey.VIEW_INVOICES,  # view-only per the sheet; Action model already caps this to VIEW
    ],
    RoleName.FINANCE: [
        PermissionKey.VIEW_EMPLOYEE_COST,
        PermissionKey.VIEW_BILLING_RATE,
        PermissionKey.VIEW_CUSTOMER_CONTRACT_VALUE,
        PermissionKey.VIEW_PROJECT_REVENUE,
        PermissionKey.VIEW_PROJECT_MARGIN,
        PermissionKey.VIEW_INVOICES,
        PermissionKey.VIEW_BANK_PAYROLL_DATA,  # "need-based" — granted; scope/UI still need-gated
    ],
    RoleName.OFFICE_ADMIN: [],
    RoleName.RECRUITER: [],
}

ROLE_DESCRIPTIONS: dict[RoleName, str] = {
    RoleName.SUPER_ADMIN: "Unrestricted system access across all modules.",
    RoleName.EMPLOYEE: "Standard employee self-service access.",
    RoleName.HR_BASIC: "HR operations excluding compensation/payroll data.",
    RoleName.HR_FULL: "Full HR access including compensation and payroll.",
    RoleName.PROJECT_MANAGER: "Manages assigned projects, their team and approvals.",
    RoleName.DELIVERY_MANAGER: "Oversees all projects and delivery-wide approvals.",
    RoleName.FINANCE: "Commercial and financial data across the organization.",
    RoleName.OFFICE_ADMIN: "Facilities, logistics and asset administration.",
    RoleName.RECRUITER: "Creates job descriptions, manages approved openings and employee referrals.",
}
