"""
Local-only mock login so the app is runnable before Google OAuth credentials
exist. The setting must be enabled explicitly in development or test.
"""

from __future__ import annotations

from hrms.config import get_settings


def dev_login_allowed() -> bool:
    settings = get_settings()
    if settings.is_production:
        return False
    return settings.ENV in {"development", "test"} and settings.HRMS_ALLOW_DEV_LOGIN
