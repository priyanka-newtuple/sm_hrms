from copy import deepcopy

import pytest

from hrms_app.errors import AppError
from hrms_app.onboarding_account_link import link
from hrms_app.employee_lifecycle import reconcile_employee, APPROVAL_TAG, COMPLETE_TAG
from test_employee_lifecycle import system
from test_performance import actor


@pytest.fixture
def existing(monkeypatch):
    p, service, workflow, enrollment = system()
    workflow['definition']['states'] = [{'name': 'Approval', 'method_refs': [{'method_id': 'approval'}]}]
    p.people = [{'id': 'existing', 'organization_id': 'org', 'email': p.data['work_email'],
                 'status': 'active', 'role': 'hrms_office_admin'}]
    monkeypatch.setenv('HRMS_EMPLOYEE_APPROVAL_FORM_ID', 'approval')
    monkeypatch.setattr('hrms_app.employee_work.employee_work', lambda *_: [
        {'entity_id': 'employee', 'workflow_id': 'workflow', 'current_state': 'Approval', 'actions': [{'trigger': 'approved'}]}])
    original = p.request
    def request(method, path, **kwargs):
        if method == 'GET':
            return deepcopy(workflow) if path.startswith('/workflow-state-machines/') else p.record('employee')
        return original(method, path, **kwargs)
    p.request = request
    p.records = lambda *_: [{'entity_id': 'employee', 'data': deepcopy(p.data)}]
    return p, service, workflow, enrollment


def test_confirmed_existing_account_preserves_access_and_password_through_completion(existing):
    p, s, w, e = existing
    link(s, actor('admin', 'superadmin'), 'employee', 'workflow', 'existing')
    link(s, actor('admin', 'superadmin'), 'employee', 'workflow', 'existing')
    assert p.data['platform_user_id'] == 'existing'
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    reconcile_employee(s, w, e, [COMPLETE_TAG])
    assert p.data['account_approved'] is True
    assert not any('/role' in path or path.startswith('/auth/') for path, _ in p.writes)
    assert s.journal.audits[0][0] == 'admin'


@pytest.mark.parametrize('failure', ['permission', 'tenant', 'pending', 'email', 'duplicate', 'stage', 'different_user'])
def test_link_rejects_unsafe_matches(existing, monkeypatch, failure):
    p, s, w, _ = existing
    who = actor('admin', 'superadmin')
    user_id = 'existing'
    if failure == 'permission':
        who = actor('employee', 'hrms_employee')
    elif failure == 'tenant':
        p.people[0]['organization_id'] = 'another-org'
    elif failure == 'pending':
        p.people[0]['status'] = 'pending'
    elif failure == 'email':
        p.people[0]['email'] = 'another@newtuple.com'
    elif failure == 'duplicate':
        p.records = lambda *_: [{'entity_id': 'other', 'data': {'platform_user_id': 'existing'}}]
    elif failure == 'stage':
        w['definition']['states'][0]['method_refs'] = []
    else:
        user_id = 'different'
    with pytest.raises(AppError):
        link(s, who, 'employee', 'workflow', user_id)
    assert not p.writes


def test_retry_after_link_write_failure_preserves_existing_access(existing):
    p, s, w, e = existing
    original = p.call
    def fail_link(method, path, **kwargs):
        if path == '/entity-records/employee':
            raise AppError(503, 'Temporary outage')
        return original(method, path, **kwargs)
    p.call = fail_link
    with pytest.raises(AppError):
        link(s, actor('admin', 'superadmin'), 'employee', 'workflow', 'existing')
    assert not p.data.get('platform_user_id')
    p.call = original
    link(s, actor('admin', 'superadmin'), 'employee', 'workflow', 'existing')
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    assert p.data['account_approved']
    assert not any('/role' in path or path.startswith('/auth/') for path, _ in p.writes)
