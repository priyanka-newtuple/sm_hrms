"""
Nested summary schemas.

List responses used to return bare UUIDs, which forced the frontend to fetch
*every* employee and *every* project just to resolve names — fragile, and it
breaks precisely when a role's scope differs between those two lists (a PM can
see an allocation's project but not necessarily every employee on it).

These summaries are embedded server-side instead. Each carries only Basic-profile
fields, so it is safe to show to anyone already entitled to see the parent record;
sensitive/commercial fields stay behind app/authz/serializers.py as before.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    designation: str
    department: str


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    status: str
    customer: CustomerSummary | None = None


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
