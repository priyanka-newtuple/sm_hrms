from __future__ import annotations

import hmac
import secrets
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hrms.auth.dev_login import dev_login_allowed
from hrms.auth.google_oauth import (
    GoogleAuthError,
    assert_allowed_domain,
    build_authorize_url,
    exchange_code_for_userinfo,
)
from hrms.auth.jwt_session import create_session_token
from hrms.auth.redirects import safe_next_path
from hrms.authz.deps import get_authz_engine, get_current_employee, get_current_user
from hrms.authz.engine import AuthzEngine
from hrms.config import get_settings
from hrms.core.exceptions import NotAuthenticated
from hrms.database import get_db
from hrms.models.employee import Employee
from hrms.models.user import User
from hrms.schemas.auth import CurrentUserOut, DevLoginRequest, FeaturePermissionOut
from hrms.seed.production_demo_data import DEMO_EMAILS

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

OAUTH_STATE_COOKIE = "hrms_oauth_state"
OAUTH_NEXT_COOKIE = "hrms_oauth_next"
OAUTH_COOKIE_MAX_AGE = 600  # 10 minutes — long enough for the Google account picker


def _cookie_flags() -> dict:
    return {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
        "path": "/",
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
        **_cookie_flags(),
    )


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, **_cookie_flags())


def _frontend_url(path: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}{path}"


def _next_cookie_value(path: str) -> str:
    # SimpleCookie quotes values that contain `/`, which then fails
    # `safe_next_path` on the way back. Percent-encode so the cookie is boring.
    return quote(path, safe="")


def _next_from_cookie(raw: str | None) -> str:
    if not raw:
        return "/"
    value = unquote(raw.strip('"'))
    return safe_next_path(value) or "/"


@router.get("/google/login")
async def google_login(next: str | None = Query(default=None)):
    """Starts Google OAuth. `state` is bound to an HttpOnly cookie so the
    callback can reject CSRF'd authorization codes. Optional `next` (a
    same-origin path) is stored separately and applied after login."""
    state = secrets.token_urlsafe(24)
    redirect = RedirectResponse(build_authorize_url(state))
    flags = _cookie_flags()
    redirect.set_cookie(OAUTH_STATE_COOKIE, state, max_age=OAUTH_COOKIE_MAX_AGE, **flags)
    safe = safe_next_path(next)
    if safe:
        redirect.set_cookie(OAUTH_NEXT_COOKIE, _next_cookie_value(safe), max_age=OAUTH_COOKIE_MAX_AGE, **flags)
    else:
        _clear_cookie(redirect, OAUTH_NEXT_COOKIE)
    return redirect


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if (
        not code
        or not state
        or not expected_state
        or len(state) != len(expected_state)
        or not hmac.compare_digest(expected_state, state)
    ):
        fail = RedirectResponse(f"{_frontend_url('/login')}?error={quote('Sign-in could not be verified. Please try again.')}")
        _clear_cookie(fail, OAUTH_STATE_COOKIE)
        _clear_cookie(fail, OAUTH_NEXT_COOKIE)
        return fail

    next_path = _next_from_cookie(request.cookies.get(OAUTH_NEXT_COOKIE))

    try:
        userinfo = await exchange_code_for_userinfo(code)
        email = userinfo["email"]
        assert_allowed_domain(email)
    except GoogleAuthError as exc:
        fail = RedirectResponse(f"{_frontend_url('/login')}?error={quote(str(exc))}")
        _clear_cookie(fail, OAUTH_STATE_COOKIE)
        _clear_cookie(fail, OAUTH_NEXT_COOKIE)
        return fail

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        fail = RedirectResponse(
            f"{_frontend_url('/login')}?error={quote(f'No employee record found for {email}. Ask an HR admin to add you first.')}"
        )
        _clear_cookie(fail, OAUTH_STATE_COOKIE)
        _clear_cookie(fail, OAUTH_NEXT_COOKIE)
        return fail
    user.google_sub = userinfo.get("sub")
    await db.commit()

    token = create_session_token(user.id, user.email)
    redirect = RedirectResponse(_frontend_url(next_path))
    _set_session_cookie(redirect, token)
    _clear_cookie(redirect, OAUTH_STATE_COOKIE)
    _clear_cookie(redirect, OAUTH_NEXT_COOKIE)
    return redirect


@router.post("/dev-login")
async def dev_login(payload: DevLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if not dev_login_allowed():
        raise NotAuthenticated("Dev login is disabled in production")

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotAuthenticated(f"No seeded user with email {payload.email}")

    token = create_session_token(user.id, user.email)
    _set_session_cookie(response, token)
    return {"ok": True}


@router.post("/demo-login")
async def demo_login(payload: DevLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower()
    if not settings.SEED_PRODUCTION_DEMO_DATA or email not in DEMO_EMAILS:
        raise NotAuthenticated("Demo login is disabled or the requested persona is invalid")

    user = (await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))).scalar_one_or_none()
    if user is None:
        raise NotAuthenticated("Demo persona is unavailable")

    token = create_session_token(user.id, user.email)
    _set_session_cookie(response, token)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    _clear_cookie(response, settings.SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/dev-users")
async def dev_users(db: AsyncSession = Depends(get_db)):
    """One seeded user per role for the dev-login picker. Disabled outside development/staging."""
    if not dev_login_allowed():
        raise NotAuthenticated("Dev login is disabled in production")
    result = await db.execute(
        select(Employee).options(selectinload(Employee.role), selectinload(Employee.user)).order_by(Employee.employee_code)
    )
    seen_roles: set[str] = set()
    personas: list[dict] = []
    for emp in result.scalars().all():
        if not emp.user or emp.role.name in seen_roles:
            continue
        seen_roles.add(emp.role.name)
        personas.append(
            {
                "email": emp.user.email,
                "full_name": emp.full_name,
                "role_name": emp.role.name,
                "department": emp.department,
            }
        )
    personas.sort(key=lambda p: p["role_name"])
    return personas


@router.get("/demo-users")
async def demo_users(db: AsyncSession = Depends(get_db)):
    """Return only the fixed demo personas when production demo mode is enabled."""
    if not settings.SEED_PRODUCTION_DEMO_DATA:
        raise NotAuthenticated("Demo login is disabled")
    result = await db.execute(
        select(Employee)
        .join(Employee.user)
        .options(selectinload(Employee.role), selectinload(Employee.user))
        .where(User.email.in_(DEMO_EMAILS), User.is_active.is_(True))
        .order_by(Employee.employee_code)
    )
    return [
        {
            "email": employee.user.email,
            "full_name": employee.full_name,
            "role_name": employee.role.name,
            "department": employee.department,
        }
        for employee in result.scalars().all()
    ]


@router.get("/me", response_model=CurrentUserOut)
async def me(
    user: User = Depends(get_current_user),
    employee: Employee = Depends(get_current_employee),
    engine: AuthzEngine = Depends(get_authz_engine),
):
    grants = await engine.get_all_feature_grants(employee)
    permission_keys = await engine.get_all_permission_keys(employee)
    return CurrentUserOut(
        user_id=user.id,
        email=user.email,
        employee_id=employee.id,
        full_name=employee.full_name,
        role_id=employee.role_id,
        role_name=employee.role.name,
        department=employee.department,
        designation=employee.designation,
        permissions=[
            FeaturePermissionOut(
                feature_key=g.feature_key.value,
                actions=[a.value for a in g.actions],
                record_scope=g.record_scope.value,
                data_profile=g.data_profile.value,
            )
            for g in grants.values()
        ],
        permission_keys=[k.value for k in permission_keys],
    )
