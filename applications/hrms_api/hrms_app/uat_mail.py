"""Restricted UAT mailbox viewer; Mailpit remains private and cannot relay mail."""
import base64
import os
import re

import httpx

from .errors import AppError
from .policy import capabilities


def enabled(actor, organization):
    return (bool(organization) and os.environ.get('HRMS_UAT_INBOX_ENABLED') == 'true'
            and os.environ.get('HRMS_EMAIL_MODE') == 'capture'
            and actor.organization_id == organization
            and bool(actor.roles & {'superadmin', 'hrms_hr_full'})
            and 'onboarding:manage' in capabilities(actor))


def authorize(actor, organization):
    if not enabled(actor, organization):
        raise AppError(404, 'UAT email inbox is not available')


def fetch(path, params=None):
    # Fixed private destination, explicit GET endpoints only; no arbitrary proxy.
    try:
        with httpx.Client(base_url='http://mailpit:8025', timeout=15, follow_redirects=False) as client:
            with client.stream('GET', '/api/v1/' + path, params=params) as response:
                if response.status_code == 404:
                    raise AppError(404, 'Email or attachment was not found')
                if response.status_code != 200:
                    raise AppError(503, 'The UAT email inbox is unavailable. Please retry.')
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 15 * 1024 * 1024:
                        raise AppError(413, 'This message or attachment is too large to preview')
                    chunks.append(chunk)
                return b''.join(chunks)
    except httpx.HTTPError:
        raise AppError(503, 'The UAT email inbox is unavailable. Please retry.') from None


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise AppError(422, 'Invalid message identifier')
    return value


def routes(app, actor_dependency, organization):
    import json
    from fastapi import Depends, Query
    from fastapi.responses import JSONResponse

    def result(value):
        return JSONResponse(value, headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'})

    @app.get('/v1/api/hrms/uat-mail/status')
    def status(current=Depends(actor_dependency)):
        return result({'enabled': enabled(current, organization)})

    @app.get('/v1/api/hrms/uat-mail/messages')
    def messages(start: int = Query(0, ge=0, le=10000), search: str = Query('', max_length=200), current=Depends(actor_dependency)):
        authorize(current, organization)
        params = {'start': start, 'limit': 50}
        if search.strip():
            params['query'] = search.strip()
        return result(json.loads(fetch('search' if search.strip() else 'messages', params)))

    @app.get('/v1/api/hrms/uat-mail/messages/{message_id}')
    def message(message_id: str, current=Depends(actor_dependency)):
        authorize(current, organization)
        return result(json.loads(fetch('message/' + identifier(message_id))))

    @app.get('/v1/api/hrms/uat-mail/messages/{message_id}/attachments/{part_id}')
    def attachment(message_id: str, part_id: str, current=Depends(actor_dependency)):
        authorize(current, organization)
        identifier(message_id)
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', part_id):
            raise AppError(422, 'Invalid attachment identifier')
        content = fetch(f'message/{message_id}/part/{part_id}')
        return result({'content': base64.b64encode(content).decode('ascii')})
