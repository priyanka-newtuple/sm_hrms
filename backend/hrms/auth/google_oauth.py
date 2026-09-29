"""
Google Workspace SSO — Authorization Code flow, domain-restricted to
@newtuple.com. The domain check happens server-side against the verified
email Google returns, not just the `hd` (hosted-domain) request parameter,
which a client could omit or spoof.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from hrms.config import get_settings

settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleAuthError(Exception):
    pass


def build_authorize_url(state: str | None = None) -> str:
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "hd": settings.ALLOWED_EMAIL_DOMAIN,
        "prompt": "select_account",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_userinfo(code: str) -> dict:
    """Exchanges the authorization code for tokens, then fetches the verified profile."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise GoogleAuthError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, "
            "or use POST /api/v1/auth/dev-login while ENV != production."
        )
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise GoogleAuthError(f"Token exchange failed: {token_resp.text}")
        access_token = token_resp.json()["access_token"]

        userinfo_resp = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if userinfo_resp.status_code != 200:
            raise GoogleAuthError(f"Userinfo fetch failed: {userinfo_resp.text}")
        return userinfo_resp.json()


def assert_allowed_domain(email: str) -> None:
    domain = email.rsplit("@", 1)[-1].lower()
    if domain != settings.ALLOWED_EMAIL_DOMAIN.lower():
        raise GoogleAuthError(f"Access restricted to @{settings.ALLOWED_EMAIL_DOMAIN} accounts.")
