"""
DataProfile + PermissionKey aware field stripping for API responses.
Applied in the service layer after a Pydantic schema has been dumped to a
dict, right before the response leaves the API — so the frontend never
receives fields a role isn't cleared for, regardless of what it renders.
"""

from __future__ import annotations

from hrms.authz.enums import DataProfile, PermissionKey

_PII_FIELDS = {"personal_email", "date_of_birth", "address"}
_COMPENSATION_FIELDS = {"salary_ctc"}
_BANK_FIELDS = {"bank_account_number", "bank_ifsc", "payroll_reference"}
_COST_FIELDS = {"employee_cost_rate"}


def strip_employee_fields(
    data: dict, profile: DataProfile, permission_keys: set[PermissionKey], *, is_self: bool = False
) -> dict:
    data = dict(data)
    if is_self:
        # A user always sees their own PII/compensation, regardless of role profile.
        return data
    if profile in (DataProfile.NONE, DataProfile.BASIC, DataProfile.LIMITED):
        for f in _PII_FIELDS | _COMPENSATION_FIELDS | _BANK_FIELDS | _COST_FIELDS:
            data.pop(f, None)
        return data
    # NON_SENSITIVE / COMMERCIAL / ALL: PII visible per profile, but sensitive
    # money/bank fields still require the explicit permission key.
    if profile == DataProfile.NON_SENSITIVE:
        for f in _COMPENSATION_FIELDS | _BANK_FIELDS | _COST_FIELDS:
            data.pop(f, None)
        return data
    if PermissionKey.VIEW_EMPLOYEE_COMPENSATION not in permission_keys:
        for f in _COMPENSATION_FIELDS:
            data.pop(f, None)
    if PermissionKey.VIEW_BANK_PAYROLL_DATA not in permission_keys:
        for f in _BANK_FIELDS:
            data.pop(f, None)
    if PermissionKey.VIEW_EMPLOYEE_COST not in permission_keys:
        for f in _COST_FIELDS:
            data.pop(f, None)
    return data


def strip_project_fields(data: dict, permission_keys: set[PermissionKey]) -> dict:
    data = dict(data)
    if PermissionKey.VIEW_BILLING_RATE not in permission_keys:
        data.pop("billing_rate", None)
    if PermissionKey.VIEW_PROJECT_REVENUE not in permission_keys:
        data.pop("revenue", None)
    if PermissionKey.VIEW_PROJECT_MARGIN not in permission_keys:
        data.pop("margin_percent", None)
    return data


def strip_customer_fields(data: dict, permission_keys: set[PermissionKey]) -> dict:
    data = dict(data)
    if PermissionKey.VIEW_CUSTOMER_CONTRACT_VALUE not in permission_keys:
        data.pop("contract_value", None)
        # Payment terms are part of the commercial contract picture.
        data.pop("payment_terms_days", None)
    return data
