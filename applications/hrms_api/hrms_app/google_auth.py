"""Browser-bound Google flow; native platform owns identity and approval decisions.

The internal platform MUST run with GOOGLE_ALLOWED_DOMAIN=newtuple.com.
Google Cloud audience must be Internal to the Newtuple Workspace organization.
"""
import os
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .errors import AppError

COOKIE = 'hrms_google_state'
COOKIE_PATH = '/v1/api/auth/google'


async def google_auth(platform, request, path):
    redirect = os.environ.get('GOOGLE_REDIRECT_URI', '')
    parsed = urlsplit(redirect)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.path != '/auth/google/callback':
        raise AppError(503, 'Google sign-in is not configured. Please use your password or contact your administrator.')
    if path == 'auth/google/url' and request.method == 'GET':
        if request.query_params.get('redirect_uri', redirect) != redirect:
            raise AppError(400, 'Please sign in from the configured HRMS website.')
        upstream = await run_in_threadpool(platform.http.get, path, params={'redirect_uri': redirect})
        if upstream.status_code != 200:
            raise AppError(503, 'Google sign-in is not configured. Please contact your administrator.')
        parts = urlsplit(upstream.json()['url'])
        if parts.scheme != 'https' or parts.netloc != 'accounts.google.com':
            raise AppError(502, 'Invalid Google sign-in configuration.')
        state = secrets.token_urlsafe(32)
        params = dict(parse_qsl(parts.query))
        params.update(state=state, hd='newtuple.com', redirect_uri=redirect)
        response = JSONResponse({'url': urlunsplit(parts._replace(query=urlencode(params)))})
        response.set_cookie(COOKIE, state, max_age=600, httponly=True, secure=True,
                            samesite='lax', path=COOKIE_PATH)
        return response
    if path != 'auth/google/callback' or request.method != 'POST':
        raise AppError(405, 'Method not allowed')
    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(400, 'Invalid sign-in request') from exc
    if not isinstance(payload, dict):
        raise AppError(400, 'Invalid sign-in request')
    state = payload.get('state')
    expected = request.cookies.get(COOKIE)
    if not isinstance(state, str) or not state.isascii() or not expected or not secrets.compare_digest(state, expected):
        raise AppError(400, 'Sign-in expired. Please return to login and try again.')
    if payload.get('redirect_uri') != redirect or not isinstance(payload.get('code'), str) or not payload['code']:
        raise AppError(400, 'Invalid sign-in request')
    upstream = await run_in_threadpool(platform.http.post, path,
                                      json={'code': payload['code'], 'redirect_uri': redirect})
    # Defense in depth: only return active tokens belonging to this HRMS tenant.
    if upstream.status_code == 200:
        data = upstream.json()
        await run_in_threadpool(platform.actor, data['access_token'])
    response = Response(upstream.content, status_code=upstream.status_code,
                        media_type='application/json')
    response.delete_cookie(COOKIE, path=COOKIE_PATH, secure=True, httponly=True, samesite='lax')
    return response
