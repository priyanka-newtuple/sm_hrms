from urllib.parse import parse_qs, unquote, urlparse

import pytest

from hrms.auth.redirects import safe_next_path


def test_safe_next_path_accepts_same_origin_paths():
    assert safe_next_path("/travel-request") == "/travel-request"
    assert safe_next_path("/referrals?role=pm") == "/referrals?role=pm"
    assert safe_next_path("/ld-calendar#week") == "/ld-calendar#week"


def test_safe_next_path_rejects_open_redirects():
    assert safe_next_path(None) is None
    assert safe_next_path("") is None
    assert safe_next_path("https://evil.example/phish") is None
    assert safe_next_path("//evil.example") is None
    assert safe_next_path("/\\evil") is None
    assert safe_next_path("travel-request") is None
    assert safe_next_path("http://hrms.invalid/login") is None


@pytest.mark.asyncio
async def test_google_login_sets_csrf_state_and_next_cookies(client):
    resp = await client.get(
        "/api/v1/auth/google/login",
        params={"next": "/travel-request"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert resp.cookies.get("hrms_oauth_state")
    next_cookie = (resp.cookies.get("hrms_oauth_next") or "").strip('"')
    assert unquote(next_cookie) == "/travel-request"
    location = urlparse(resp.headers["location"])
    assert location.netloc == "accounts.google.com"
    state = parse_qs(location.query).get("state", [None])[0]
    assert state == resp.cookies["hrms_oauth_state"]


@pytest.mark.asyncio
async def test_google_login_rejects_open_redirect_next(client):
    resp = await client.get(
        "/api/v1/auth/google/login",
        params={"next": "https://evil.example/phish"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    set_cookie = "\n".join(resp.headers.get_list("set-cookie"))
    assert "evil.example" not in set_cookie


@pytest.mark.asyncio
async def test_google_callback_rejects_missing_state(client):
    resp = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "not-a-real-code", "state": "forged"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "/login" in location
    assert "error=" in location


@pytest.mark.asyncio
async def test_logout_clears_session_cookie(client, seeded):
    login = await client.post(
        "/api/v1/auth/dev-login", json={"email": "sanjay.bhat@newtuple.com"}
    )
    assert login.status_code == 200
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200

    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    after = await client.get("/api/v1/auth/me")
    assert after.status_code == 401
