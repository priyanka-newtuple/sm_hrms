from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.auth.jwt_session import InvalidSessionToken, decode_session_token
from hrms.authz.engine import AuthzEngine
from hrms.authz.enums import Action, FeatureKey, PermissionKey
from hrms.config import get_settings
from hrms.core.exceptions import NotAuthenticated, PermissionDenied
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.models.user import User

settings = get_settings()


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ")
    if not token:
        raise NotAuthenticated()
    try:
        payload = decode_session_token(token)
    except InvalidSessionToken as exc:
        raise NotAuthenticated("Session expired or invalid") from exc

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise NotAuthenticated("Account not found or inactive")
    return user


async def get_current_employee(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Employee:
    result = await db.execute(select(Employee).options(selectinload(Employee.role)).where(Employee.user_id == user.id))
    employee = result.scalar_one_or_none()
    if employee is None:
        raise NotAuthenticated("No employee profile linked to this account")
    return employee


async def get_authz_engine(db: AsyncSession = Depends(get_db)) -> AuthzEngine:
    return AuthzEngine(db)


def require_permission(feature: FeatureKey, action: Action):
    """
    FastAPI dependency factory. Usage: `Depends(require_permission(FeatureKey.PROJECTS, Action.EDIT))`.
    This is the server-side enforcement boundary — it runs independently of
    whatever the frontend chose to render.
    """

    async def _checker(
        employee: Employee = Depends(get_current_employee),
        engine: AuthzEngine = Depends(get_authz_engine),
    ) -> Employee:
        if not await engine.has_permission(employee, feature, action):
            raise PermissionDenied(f"Role '{employee.role.name}' cannot '{action.value}' on '{feature.value}'")
        return employee

    return _checker


def require_permission_key(key: PermissionKey):
    async def _checker(
        employee: Employee = Depends(get_current_employee),
        engine: AuthzEngine = Depends(get_authz_engine),
    ) -> bool:
        return await engine.has_permission_key(employee, key)

    return _checker
