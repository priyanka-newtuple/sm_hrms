"""
Matrix-driven checks against the seeded permission data itself (no DB needed —
these validate app/seed/permission_matrix.py, which is what actually gets
loaded into role_feature_permissions / role_permission_keys).
"""

from hrms.authz.enums import Action, FeatureKey, RecordScope, RoleName
from hrms.seed.permission_matrix import FEATURE_PERMISSIONS, ROLE_PERMISSION_KEYS


def test_every_role_has_every_feature_defined():
    for role in RoleName:
        assert set(FEATURE_PERMISSIONS[role].keys()) == set(FeatureKey), f"{role} missing features"


def test_super_admin_has_full_access_everywhere():
    for _feature, (actions, scope, _profile) in FEATURE_PERMISSIONS[RoleName.SUPER_ADMIN].items():
        assert actions == [Action.FULL]
        assert scope == RecordScope.ALL


def test_employee_has_no_access_to_customers():
    actions, scope, _ = FEATURE_PERMISSIONS[RoleName.EMPLOYEE][FeatureKey.CUSTOMERS]
    assert actions == [Action.NONE]
    assert scope == RecordScope.NONE


def test_employee_self_scope_on_directory():
    actions, scope, _ = FEATURE_PERMISSIONS[RoleName.EMPLOYEE][FeatureKey.EMPLOYEE_DIRECTORY]
    assert scope == RecordScope.SELF
    assert Action.VIEW in actions and Action.EDIT in actions


def test_office_admin_cannot_approve_expenses():
    actions, _, _ = FEATURE_PERMISSIONS[RoleName.OFFICE_ADMIN][FeatureKey.EXPENSE_MANAGEMENT]
    assert Action.APPROVE not in actions


def test_project_manager_approves_only_assigned_timesheets():
    actions, scope, _ = FEATURE_PERMISSIONS[RoleName.PROJECT_MANAGER][FeatureKey.TIMESHEETS]
    assert Action.APPROVE in actions
    assert scope == RecordScope.ASSIGNED


def test_delivery_manager_approves_all_timesheets():
    actions, scope, _ = FEATURE_PERMISSIONS[RoleName.DELIVERY_MANAGER][FeatureKey.TIMESHEETS]
    assert Action.APPROVE in actions
    assert scope == RecordScope.ALL


def test_only_finance_and_delivery_manager_and_super_admin_get_project_margin_key():
    from hrms.authz.enums import PermissionKey

    granted_roles = {
        role for role, keys in ROLE_PERMISSION_KEYS.items() if PermissionKey.VIEW_PROJECT_MARGIN in keys
    }
    assert granted_roles == {
        RoleName.SUPER_ADMIN,
        RoleName.DELIVERY_MANAGER,
        RoleName.FINANCE,
        RoleName.PROJECT_MANAGER,
    }


def test_hr_basic_does_not_get_compensation_key_but_hr_full_does():
    from hrms.authz.enums import PermissionKey

    assert PermissionKey.VIEW_EMPLOYEE_COMPENSATION not in ROLE_PERMISSION_KEYS[RoleName.HR_BASIC]
    assert PermissionKey.VIEW_EMPLOYEE_COMPENSATION in ROLE_PERMISSION_KEYS[RoleName.HR_FULL]
