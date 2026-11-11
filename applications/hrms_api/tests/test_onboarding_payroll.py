from contextlib import nullcontext
from types import SimpleNamespace
import hashlib
import json

import httpx
import pytest

from hrms_app import onboarding_payroll as payroll
from hrms_app.errors import AppError


class Database:
    def __init__(self): self.row = None
    def execute(self, sql, args=()):
        if sql.startswith('SELECT'): return SimpleNamespace(fetchone=lambda: self.row)
        if sql.startswith('INSERT'):
            self.row = (1, args[2], args[3], None)
            return SimpleNamespace(fetchone=lambda: (1,))
        if sql.startswith('UPDATE'): self.row = (*self.row[:3], args[0].obj)
        return SimpleNamespace(fetchone=lambda: None)


def employee(**extra):
    return {'organization_id': 'org', 'data': {
        'first_name': 'Test', 'last_name': 'Employee', 'work_email': 'Employee@Example.com',
        'employment_type': 'fte', 'employee_code': 'EMP-0042', 'date_joined': '2026-11-03T00:00:00',
        'designation': 'Engineer', 'department': 'Delivery', 'phone': '9810012345',
        'bank_account_number': '1234567890', 'bank_ifsc': 'HDFC0001234',
        'reports_to_employee_code': 'EMP-0007', **extra}}


def fixture(monkeypatch, record=None, others=()):
    monkeypatch.setenv('HRMS_RAZORPAY_MODE', 'mock')
    db, writes = Database(), []
    record = record or employee()
    manager = {'entity_id': 'manager', 'data': {'employee_code': 'EMP-0007', 'razorpay_employee_id': '7', 'razorpay_mode': 'mock'}}
    rows = [manager, *others]

    def request(method, path, **kwargs):
        assert kwargs['token'] == 'human'
        if method == 'GET': return record
        writes.append(kwargs['json']['data'])
    platform = SimpleNamespace(request=request, records=lambda kind, fields: rows)
    actor = SimpleNamespace(organization_id='org', token='human')
    journal = SimpleNamespace(lock=lambda org: nullcontext(db), audit=lambda *args: None)
    return platform, journal, actor, record, writes, db


def sent(db):
    return [(r['sub-type'], r['data']) for r in db.row[3]['mock_requests']]


def test_mock_creates_then_sets_number_and_profile_and_retry_reuses_receipt(monkeypatch):
    p, j, a, _r, w, db = fixture(monkeypatch)
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: pytest.fail('mock must not contact the provider'))
    first = payroll.register(p, j, a, 'employee')
    # The suggestion follows the HRMS code: EMP-0042 -> 42.
    assert first == {'razorpay_employee_id': '42', 'razorpay_people_id': 'mock-1', 'razorpay_mode': 'mock'}
    calls = sent(db)
    assert calls[0] == ('create', {'email': 'employee@example.com', 'name': 'Test Employee', 'type': 'employee'})
    assert calls[1] == ('edit', {'email': 'employee@example.com', 'employee-id': 42, 'hiring-date': '2026-11-03',
                                 'title': 'Engineer', 'department': 'Delivery', 'phone-number': '9810012345',
                                 'bank-account-number': '<provided>', 'bank-ifsc': '<provided>',
                                 'manager-employee-id': 7, 'manager-employee-type': 'employee'})
    monkeypatch.setattr(payroll, 'send', lambda *a: pytest.fail('a retry must not call the provider again'))
    assert payroll.register(p, j, a, 'employee') == first
    assert len(w) == 2


def test_hr_number_is_used_and_validated(monkeypatch):
    others = [{'entity_id': 'other', 'data': {'razorpay_employee_id': '43'}}]
    p, j, a, r, w, db = fixture(monkeypatch, employee(razorpay_employee_id='108'), others)
    assert payroll.register(p, j, a, 'employee')['razorpay_employee_id'] == '108'
    for value, status in [('43', 409), ('0', 422), ('EMP-9', 422), ('-5', 422)]:
        p, j, a, _r, _w, db = fixture(monkeypatch, employee(razorpay_employee_id=value), others)
        with pytest.raises(AppError) as error:
            payroll.register(p, j, a, 'employee')
        assert error.value.status == status
        assert db.row is None  # nothing reaches the provider


def test_suggestion_skips_numbers_already_used():
    rows = [{'entity_id': 'a', 'data': {'razorpay_employee_id': '42'}},
            {'entity_id': 'b', 'data': {'razorpay_employee_id': '57'}}]
    assert payroll.suggest({'employee_code': 'EMP-0042'}, rows, 'new') == 58
    assert payroll.suggest({'employee_code': 'EMP-0042'}, rows, 'a') == 42  # its own number is not "taken"
    assert payroll.suggest({'employee_code': 'NT-A'}, [], 'new') == 1


def test_unconfigured_profile_fields_and_unregistered_manager_are_not_sent(monkeypatch):
    record = employee(phone='', bank_account_number=None, bank_ifsc=None, reports_to_employee_code='EMP-0099')
    p, j, a, _r, _w, db = fixture(monkeypatch, record)
    payroll.register(p, j, a, 'employee')
    edit = sent(db)[1][1]
    assert not {'phone-number', 'bank-account-number', 'bank-ifsc', 'pan', 'manager-employee-id'} & set(edit)


def test_lost_create_reply_is_confirmed_by_email_never_recreated(monkeypatch):
    p, j, a, _r, w, _db = fixture(monkeypatch)
    real = payroll.send
    def lost(mode, sub_type, data, receipt):
        if sub_type == 'create': raise httpx.ReadTimeout('timeout')
        return real(mode, sub_type, data, receipt)
    monkeypatch.setattr(payroll, 'send', lost)
    with pytest.raises(AppError, match='could not be confirmed') as error:
        payroll.register(p, j, a, 'employee')
    assert error.value.status == 502 and not w
    calls = []
    monkeypatch.setattr(payroll, 'send', lambda mode, sub_type, data, receipt: calls.append((sub_type, data)) or {'status': 'ok'})
    result = payroll.register(p, j, a, 'employee')
    assert [c[0] for c in calls] == ['edit', 'edit']  # confirm by email, then profile; never create
    assert calls[0][1] == {'email': 'employee@example.com', 'employee-id': 42}
    assert result['razorpay_employee_id'] == '42' and result['razorpay_people_id'] == ''


def test_person_missing_after_lost_reply_stays_blocked(monkeypatch):
    p, j, a, _r, w, db = fixture(monkeypatch)
    def failing(mode, sub_type, data, receipt): raise ValueError('Provider did not confirm the request')
    monkeypatch.setattr(payroll, 'send', failing)
    with pytest.raises(AppError): payroll.register(p, j, a, 'employee')
    with pytest.raises(AppError, match='administrator must check') as error:
        payroll.register(p, j, a, 'employee')
    assert error.value.status == 409 and db.row[3] is None and not w


def test_failed_profile_edit_retries_without_recreating(monkeypatch):
    p, j, a, _r, _w, db = fixture(monkeypatch)
    real = payroll.send
    def edit_fails(mode, sub_type, data, receipt):
        if sub_type == 'edit': raise ValueError('Provider did not confirm the request')
        return real(mode, sub_type, data, receipt)
    monkeypatch.setattr(payroll, 'send', edit_fails)
    with pytest.raises(AppError, match='will not be created again'):
        payroll.register(p, j, a, 'employee')
    assert db.row[3]['people-id'] == 'mock-1' and not db.row[3].get('profile_applied')
    monkeypatch.setattr(payroll, 'send', lambda mode, sub_type, data, receipt: (
        pytest.fail('must not create again') if sub_type == 'create' else {'status': 'ok'}))
    assert payroll.register(p, j, a, 'employee')['razorpay_people_id'] == 'mock-1'
    assert db.row[3]['profile_applied']


@pytest.mark.parametrize('change', ['tenant', 'payload', 'number', 'mode'])
def test_receipt_isolation(monkeypatch, change):
    p, j, a, r, _w, db = fixture(monkeypatch)
    payroll.register(p, j, a, 'employee')
    db.row = (*db.row[:3], {**db.row[3], 'profile_applied': False})
    if change == 'tenant': r['organization_id'] = 'another'
    if change == 'payload': r['data']['work_email'] = 'different@example.com'
    if change == 'mode':
        monkeypatch.setenv('HRMS_RAZORPAY_MODE', 'live')
        monkeypatch.setenv('HRMS_RAZORPAY_API_ID', '123')
        monkeypatch.setenv('HRMS_RAZORPAY_API_KEY', 'test-key')
    if change == 'number':
        db.row = (*db.row[:3], {**db.row[3], 'number': 99})  # recorded number differs from these details
    monkeypatch.setattr(payroll, 'send', lambda *a: pytest.fail('must not call the provider'))
    with pytest.raises(AppError): payroll.register(p, j, a, 'employee')


def test_already_registered_employee_needs_reconciliation(monkeypatch):
    p, j, a, _r, _w, db = fixture(monkeypatch, employee(razorpay_employee_id='42', razorpay_mode='mock'))
    with pytest.raises(AppError, match='reconciliation') as error:
        payroll.register(p, j, a, 'employee')
    assert error.value.status == 409 and db.row is None


def test_live_exact_people_api_contract(monkeypatch):
    monkeypatch.setenv('HRMS_RAZORPAY_API_ID', '2631')
    monkeypatch.setenv('HRMS_RAZORPAY_API_KEY', 'test-key')
    bodies = []
    def post(url, **kw):
        assert url == 'https://payroll.razorpay.com/api/people' and kw['follow_redirects'] is False
        bodies.append(kw['json'])
        reply = {'status': 'ok', 'people-id': 36286, 'employee-id': 4} if kw['json']['request']['sub-type'] == 'create' else {'status': 'ok'}
        return httpx.Response(200, json=reply, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx, 'post', post)
    receipt = {'id': 1}
    assert payroll.send('live', 'create', {'email': 'e@x.com', 'name': 'E', 'type': 'employee'}, receipt)['people-id'] == 36286
    payroll.send('live', 'edit', {'email': 'e@x.com', 'employee-id': 42}, receipt)
    assert bodies[0] == {'auth': {'id': 2631, 'key': 'test-key'}, 'request': {'type': 'people', 'sub-type': 'create'},
                         'data': {'email': 'e@x.com', 'name': 'E', 'type': 'employee'}}
    assert bodies[1]['request'] == {'type': 'people', 'sub-type': 'edit'}
    assert 'mock_requests' not in receipt  # live never keeps request bodies


def test_live_rejection_is_not_treated_as_success(monkeypatch):
    monkeypatch.setenv('HRMS_RAZORPAY_API_ID', '2631')
    monkeypatch.setenv('HRMS_RAZORPAY_API_KEY', 'test-key')
    monkeypatch.setattr(httpx, 'post', lambda url, **kw: httpx.Response(
        200, json={'status': 'error', 'error': 'Duplicate'}, request=httpx.Request('POST', url)))
    with pytest.raises(ValueError):
        payroll.send('live', 'create', {'email': 'e@x.com', 'name': 'E', 'type': 'employee'}, {'id': 1})


@pytest.mark.parametrize('mode', ['disabled', 'sandbox', 'anything'])
def test_unsafe_modes_fail_closed(monkeypatch, mode):
    p, j, a, _r, _w, db = fixture(monkeypatch)
    monkeypatch.setenv('HRMS_RAZORPAY_MODE', mode)
    with pytest.raises(AppError): payroll.register(p, j, a, 'employee')
    assert db.row is None


def test_writeback_denial_preserves_receipt_and_retries_without_recreating(monkeypatch):
    p, j, a, _r, w, db = fixture(monkeypatch)
    original = p.request
    def denied(method, path, **kwargs):
        if method == 'PUT':
            raise AppError(403, 'Not allowed to edit read-only fields')
        return original(method, path, **kwargs)
    p.request = denied
    with pytest.raises(AppError, match='existing registration will be reused') as error:
        payroll.register(p, j, a, 'employee')
    assert error.value.status == 403 and db.row[3]['profile_applied'] and not w
    p.request = original
    monkeypatch.setattr(payroll, 'send', lambda *args: pytest.fail('must reuse the receipt'))
    assert payroll.register(p, j, a, 'employee')['razorpay_employee_id'] == '42'
    assert len(w) == 1


def test_create_only_release_receipts_keep_their_ids(monkeypatch):
    p, j, a, r, _w, db = fixture(monkeypatch)
    created = payroll.person(r['data'])
    fingerprint = hashlib.sha256(json.dumps(created, sort_keys=True).encode()).hexdigest()
    db.row = (1, 'mock', fingerprint, {'status': 'ok', 'people-id': 1, 'employee-id': 1})
    monkeypatch.setattr(payroll, 'send', lambda *args: pytest.fail('legacy receipts are not re-sent'))
    assert payroll.register(p, j, a, 'employee') == {
        'razorpay_employee_id': '1', 'razorpay_people_id': '1', 'razorpay_mode': 'mock'}


def test_release_does_not_globally_lock_integration_result_fields():
    from pathlib import Path
    package = next((parent / 'configuration/hrms/release.json' for parent in Path(__file__).resolve().parents
                    if (parent / 'configuration/hrms/release.json').is_file()), None)
    if package is None:
        pytest.skip('Release configuration is validated separately outside the application image')
    release = json.loads(package.read_text(encoding='utf-8'))
    fields = {obj['match']: obj['payload'] for obj in release['objects'] if obj['kind'] == 'field'}
    for key in payroll.FIELDS:
        assert fields[key]['settings']['read_only'] is False
