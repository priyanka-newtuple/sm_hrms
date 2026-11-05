"""Razorpay Payroll adapter with durable, tenant-scoped creation receipts.

Mock/live share orchestration. A timed-out live create is never blindly repeated.
Only application-owned tables are accessed here.
"""
from contextlib import nullcontext
import hashlib
import json
import re
import os

import httpx
from psycopg.types.json import Jsonb

from .errors import AppError

FIELDS = ('razorpay_employee_id', 'razorpay_people_id', 'razorpay_mode')


def mode():
    value = os.getenv('HRMS_RAZORPAY_MODE', 'disabled').strip().lower()
    if value not in {'disabled', 'mock', 'live'}:
        raise AppError(503, 'Invalid payroll integration mode')
    return value


def payload(data):
    name = ' '.join(str(data.get(k) or '').strip() for k in ('first_name', 'last_name')).strip()
    email = str(data.get('work_email') or '').strip().lower()
    kind = str(data.get('employment_type') or '').strip().lower()
    types = {'fte': 'employee', 'employee': 'employee', 'contractor': 'contractor'}
    if not name or '@' not in email or kind not in types:
        raise AppError(422, 'Payroll requires name, work email and employment type (FTE or Contractor)')
    return {'email': email, 'name': name, 'type': types[kind]}


def credentials():
    identity = os.getenv('HRMS_RAZORPAY_API_ID', '')
    key = os.getenv('HRMS_RAZORPAY_API_KEY', '')
    if not re.fullmatch(r'[0-9]+', identity) or not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise AppError(503, 'Live Payroll credentials are not configured')
    return {'id': int(identity), 'key': key}


def create_person(selected_mode, data, mock_id):
    if selected_mode not in {'mock', 'live'}:
        raise AppError(409, 'Payroll creation requires mock or live mode')
    if selected_mode == 'mock':
        return {'status': 'ok', 'people-id': mock_id, 'employee-id': mock_id}
    auth = credentials()
    # Endpoint is fixed: no caller-controlled URL or redirect can receive credentials.
    response = httpx.post('https://payroll.razorpay.com/api/people', timeout=30,
                          follow_redirects=False, json={'auth': auth,
                          'request': {'type': 'people', 'sub-type': 'create'}, 'data': data})
    response.raise_for_status()
    return response.json()


def register(platform, journal, actor, entity_id, *, db=None):
    selected_mode = mode()
    if selected_mode == 'disabled':
        raise AppError(409, 'Payroll integration is disabled. Configure mock or live mode before approving.')
    if selected_mode == 'live':
        credentials()
    with (nullcontext(db) if db is not None else journal.lock(actor.organization_id)) as db:
        record = platform.request('GET', '/entity-records/' + entity_id, token=actor.token)
        if record['organization_id'] != actor.organization_id:
            raise AppError(403, 'Employee organization mismatch')
        data = payload(record['data'])
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        db.execute('''CREATE TABLE IF NOT EXISTS hrms_payroll_receipts (
            id bigserial UNIQUE, organization_id text NOT NULL, employee_id text NOT NULL,
            mode text NOT NULL, fingerprint text NOT NULL, outcome jsonb,
            PRIMARY KEY (organization_id, employee_id))''')
        row = db.execute('''SELECT id, mode, fingerprint, outcome FROM hrms_payroll_receipts
            WHERE organization_id=%s AND employee_id=%s''', (actor.organization_id, entity_id)).fetchone()
        if row and (row[1] != selected_mode or row[2] != fingerprint):
            raise AppError(409, 'Payroll registration already started with different details or mode; reconcile it before retrying')
        if row and row[3] is None:
            raise AppError(409, 'Payroll creation outcome is uncertain. An administrator must reconcile it before retrying')
        if not row:
            if record['data'].get('razorpay_employee_id'):
                raise AppError(409, 'An existing Payroll ID requires reconciliation before registration')
            number = db.execute('''INSERT INTO hrms_payroll_receipts
                (organization_id, employee_id, mode, fingerprint) VALUES (%s,%s,%s,%s) RETURNING id''',
                (actor.organization_id, entity_id, selected_mode, fingerprint)).fetchone()[0]
            try:
                outcome = create_person(selected_mode, data, number)
                if not isinstance(outcome, dict):
                    raise ValueError('Invalid provider response')
                if outcome.get('status') != 'ok' or not all(outcome.get(k) for k in ('people-id', 'employee-id')):
                    raise ValueError('Invalid provider response')
            except (httpx.HTTPError, ValueError, AppError) as exc:
                raise AppError(502, 'Payroll registration could not be confirmed; reconcile the provider result before retrying') from exc
            db.execute('''UPDATE hrms_payroll_receipts SET outcome=%s
                WHERE organization_id=%s AND employee_id=%s''', (Jsonb(outcome), actor.organization_id, entity_id))
            journal.audit(db, actor, 'employee.payroll.registered.' + selected_mode, entity_id)
        else:
            outcome = row[3]
        # Receipt survives write-back/transition failure. A retry reuses it, including by another admin.
        values = dict(zip(FIELDS, (str(outcome['employee-id']), str(outcome['people-id']), selected_mode)))
        try:
            platform.request('PUT', '/entity-records/' + entity_id, token=actor.token, json={'data': values})
        except AppError as exc:
            raise AppError(exc.status, 'Payroll registration is recorded, but its IDs could not be saved to HRMS. '
                           'Ask an administrator to check the Payroll field configuration and permissions, '
                           'then retry this handover. The existing registration will be reused.') from exc
        return values
