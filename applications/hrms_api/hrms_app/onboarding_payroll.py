"""Razorpay Payroll registration with durable, tenant-scoped receipts.

Provider contract (RazorpayX Payroll API, POST https://payroll.razorpay.com/api/people):
`create` accepts only email, name and type and returns `people-id` and a
provider-assigned `employee-id`; `edit` identifies the person by email and sets the
employer's employee number plus profile details. HRMS therefore creates, then edits.

Mock and live share the orchestration. A timed-out live create is never blindly
repeated: a retry confirms the person through edit-by-email instead. Only
application-owned tables are accessed here; field and form definitions are native.
"""
from contextlib import nullcontext
import hashlib
import json
import os
import re

import httpx
from psycopg.types.json import Jsonb

from .errors import AppError

NUMBER = 'razorpay_employee_id'  # The employee number, suggested to and confirmed by HR.
RESULTS = ('razorpay_people_id', 'razorpay_mode')  # Written only by registration.
FIELDS = (NUMBER, *RESULTS)
URL = 'https://payroll.razorpay.com/api/people'
# Razorpay `edit` keys taken from native Employee fields when the tenant has configured them.
PROFILE = {'hiring-date': 'date_joined', 'title': 'designation', 'department': 'department',
           'phone-number': 'phone', 'pan': 'pan_number', 'bank-account-number': 'bank_account_number',
           'bank-ifsc': 'bank_ifsc'}
SENSITIVE = {'pan', 'bank-account-number', 'bank-ifsc'}
EMPLOYEE_FIELDS = ['employee_code', 'reports_to_employee_code', *FIELDS]


def mode():
    value = os.getenv('HRMS_RAZORPAY_MODE', 'disabled').strip().lower()
    if value not in {'disabled', 'mock', 'live'}:
        raise AppError(503, 'Invalid payroll integration mode')
    return value


def registered(data):
    return bool(data.get('razorpay_mode'))


def person(data):
    name = ' '.join(str(data.get(k) or '').strip() for k in ('first_name', 'last_name')).strip()
    email = str(data.get('work_email') or '').strip().lower()
    kind = str(data.get('employment_type') or '').strip().lower()
    types = {'fte': 'employee', 'employee': 'employee', 'contractor': 'contractor'}
    if not name or '@' not in email or kind not in types:
        raise AppError(422, 'Payroll requires name, work email and employment type (FTE or Contractor)')
    return {'email': email, 'name': name, 'type': types[kind]}


def taken(employees, entity_id):
    """Employee numbers already used by other employees in this tenant."""
    result = set()
    for row in employees:
        value = str(row['data'].get(NUMBER) or '')
        if row['entity_id'] != entity_id and value.isdigit():
            result.add(int(value))
    return result


def suggest(data, employees, entity_id):
    """The next number: the digits of the HRMS employee code (EMP-0042 -> 42) when free."""
    used = taken(employees, entity_id)
    digits = re.search(r'(\d+)$', str(data.get('employee_code') or ''))
    if digits and int(digits.group(1)) > 0 and int(digits.group(1)) not in used:
        return int(digits.group(1))
    return max(used, default=0) + 1


def number(data, employees, entity_id):
    """HR's number, or the suggestion when HR accepted it without editing."""
    value = data.get(NUMBER)
    if value in (None, ''):
        return suggest(data, employees, entity_id)
    if not re.fullmatch(r'0*[1-9][0-9]{0,8}', str(value).strip()):
        raise AppError(422, 'Employee number must be a positive whole number')
    if int(value) in taken(employees, entity_id):
        raise AppError(409, f'Employee number {int(value)} is already used by another employee')
    return int(value)


def profile(data, employees, chosen):
    """Razorpay `edit` details; empty or unconfigured fields are simply not sent."""
    details = {'email': person(data)['email'], 'employee-id': chosen}
    for key, field in PROFILE.items():
        value = str(data.get(field) or '').strip()
        if value:
            details[key] = value[:10] if key == 'hiring-date' else value
    manager = next((r['data'] for r in employees if data.get('reports_to_employee_code')
                    and r['data'].get('employee_code') == data['reports_to_employee_code']), {})
    if registered(manager) and str(manager.get(NUMBER) or '').isdigit():
        details.update({'manager-employee-id': int(manager[NUMBER]), 'manager-employee-type': 'employee'})
    return details


def credentials():
    identity = os.getenv('HRMS_RAZORPAY_API_ID', '')
    key = os.getenv('HRMS_RAZORPAY_API_KEY', '')
    if not re.fullmatch(r'[0-9]+', identity) or not re.fullmatch(r'[A-Za-z0-9_-]+', key):
        raise AppError(503, 'Live Payroll credentials are not configured')
    return {'id': int(identity), 'key': key}


def send(selected_mode, sub_type, data, receipt):
    """One People API call. Mock answers like the provider and keeps what it would send."""
    if selected_mode not in {'mock', 'live'}:
        raise AppError(409, 'Payroll creation requires mock or live mode')
    if selected_mode == 'mock':
        # Bank and tax identifiers are never stored, only that they would have been sent.
        shown = {k: ('<provided>' if k in SENSITIVE else v) for k, v in data.items()}
        receipt.setdefault('mock_requests', []).append({'sub-type': sub_type, 'data': shown})
        if sub_type == 'create':
            return {'status': 'ok', 'people-id': f"mock-{receipt['id']}", 'employee-id': receipt['id']}
        return {'status': 'ok'}
    # Endpoint is fixed: no caller-controlled URL or redirect can receive credentials.
    response = httpx.post(URL, timeout=30, follow_redirects=False, json={
        'auth': credentials(), 'request': {'type': 'people', 'sub-type': sub_type}, 'data': data})
    response.raise_for_status()
    outcome = response.json()
    if not isinstance(outcome, dict) or outcome.get('status') != 'ok':
        raise ValueError('Provider did not confirm the request')
    return outcome


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
        data = record['data']
        employees = platform.records('HRMS.Employee', EMPLOYEE_FIELDS)
        created = person(data)
        db.execute('''CREATE TABLE IF NOT EXISTS hrms_payroll_receipts (
            id bigserial UNIQUE, organization_id text NOT NULL, employee_id text NOT NULL,
            mode text NOT NULL, fingerprint text NOT NULL, outcome jsonb,
            PRIMARY KEY (organization_id, employee_id))''')
        row = db.execute('''SELECT id, mode, fingerprint, outcome FROM hrms_payroll_receipts
            WHERE organization_id=%s AND employee_id=%s''', (actor.organization_id, entity_id)).fetchone()
        if row and row[3] and 'number' not in row[3]:
            return writeback(platform, actor, entity_id, legacy(row, created, selected_mode))
        chosen = int(row[3]['number']) if row and row[3] else number(data, employees, entity_id)
        fingerprint = hashlib.sha256(json.dumps({**created, 'number': chosen}, sort_keys=True).encode()).hexdigest()
        if row and (row[1] != selected_mode or row[2] != fingerprint):
            raise AppError(409, 'Payroll registration already started with different details or mode; reconcile it before retrying')
        if not row and registered(data):
            raise AppError(409, 'An existing Payroll registration requires reconciliation before registering again')

        def save(outcome):
            db.execute('UPDATE hrms_payroll_receipts SET outcome=%s WHERE organization_id=%s AND employee_id=%s',
                       (Jsonb(outcome), actor.organization_id, entity_id))

        if not row:
            receipt_id = db.execute('''INSERT INTO hrms_payroll_receipts
                (organization_id, employee_id, mode, fingerprint) VALUES (%s,%s,%s,%s) RETURNING id''',
                (actor.organization_id, entity_id, selected_mode, fingerprint)).fetchone()[0]
            outcome = {'id': receipt_id, 'number': chosen}
            try:
                reply = send(selected_mode, 'create', created, outcome)
                if not reply.get('people-id'):
                    raise ValueError('Provider did not return a people ID')
            except (httpx.HTTPError, ValueError, AppError) as exc:
                raise AppError(502, 'Payroll registration could not be confirmed. Retry: HRMS will confirm the '
                                    'person by email before doing anything else.') from exc
            outcome['people-id'] = reply['people-id']
            save(outcome)
            journal.audit(db, actor, 'employee.payroll.registered.' + selected_mode, entity_id)
        elif not row[3]:
            # The create may have succeeded without a reply. Editing by email succeeds only
            # if the person exists, so it confirms them without creating a duplicate.
            outcome = {'id': row[0], 'number': chosen, 'people-id': None, 'confirmed_by_email': True}
            try:
                send(selected_mode, 'edit', {'email': created['email'], 'employee-id': chosen}, outcome)
            except (httpx.HTTPError, ValueError, AppError) as exc:
                raise AppError(409, 'Payroll creation outcome is uncertain and the person could not be found by '
                                    'email. An administrator must check Razorpay Payroll before retrying.') from exc
            save(outcome)
            journal.audit(db, actor, 'employee.payroll.confirmed.' + selected_mode, entity_id)
        else:
            outcome = dict(row[3])
        if not outcome.get('profile_applied'):
            # Sets the employee number and details; safe to repeat until it succeeds.
            try:
                send(selected_mode, 'edit', profile(data, employees, chosen), outcome)
            except (httpx.HTTPError, ValueError, AppError) as exc:
                raise AppError(502, 'The Payroll person exists, but their employee number and details could not be '
                                    'saved. Retry; the person will not be created again.') from exc
            outcome['profile_applied'] = True
            save(outcome)
        return writeback(platform, actor, entity_id, {
            NUMBER: str(chosen), 'razorpay_people_id': str(outcome.get('people-id') or ''), 'razorpay_mode': selected_mode})


def legacy(row, created, selected_mode):
    """Receipts from the create-only release keep the provider's IDs; nothing is re-sent."""
    if row[1] != selected_mode or row[2] != hashlib.sha256(json.dumps(created, sort_keys=True).encode()).hexdigest():
        raise AppError(409, 'Payroll registration already started with different details or mode; reconcile it before retrying')
    return {NUMBER: str(row[3]['employee-id']), 'razorpay_people_id': str(row[3]['people-id']), 'razorpay_mode': selected_mode}


def writeback(platform, actor, entity_id, values):
    # The receipt survives write-back/transition failure. A retry reuses it, including by another admin.
    try:
        platform.request('PUT', '/entity-records/' + entity_id, token=actor.token, json={'data': values})
    except AppError as exc:
        raise AppError(exc.status, 'Payroll registration is recorded, but its IDs could not be saved to HRMS. '
                       'Ask an administrator to check the Payroll field configuration and permissions, '
                       'then retry this handover. The existing registration will be reused.') from exc
    return values
