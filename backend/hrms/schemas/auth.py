from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class DevLoginRequest(BaseModel):
    email: EmailStr


class FeaturePermissionOut(BaseModel):
    feature_key: str
    actions: list[str]
    record_scope: str
    data_profile: str


class CurrentUserOut(BaseModel):
    user_id: uuid.UUID
    email: str
    employee_id: uuid.UUID
    full_name: str
    role_id: uuid.UUID
    role_name: str
    department: str
    designation: str
    permissions: list[FeaturePermissionOut]
    permission_keys: list[str]
