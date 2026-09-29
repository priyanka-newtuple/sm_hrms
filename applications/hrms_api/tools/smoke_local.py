"""Local-only integration verification. Creates a named fixture hire and request."""
import os

import httpx

from hrms_app.platform import PlatformClient


def main():
    if os.environ.get('HRMS_LOCAL_SMOKE') != 'true':
        raise RuntimeError('This test is restricted to the isolated local stack')
    app = httpx.Client(base_url='http://hrms-app:8000/v1/api', timeout=120)
    login = app.post('/auth/login', json={'email': os.environ['HRMS_INSTALL_EMAIL'], 'password': os.environ['HRMS_INSTALL_PASSWORD']})
    assert login.status_code == 200, login.text
    admin = {'Authorization': 'Bearer ' + login.json()['access_token']}
    caps = app.get('/hrms/capabilities', headers=admin)
    assert caps.status_code == 200 and 'employee:create' in caps.json()['capabilities'], caps.text
    employees = app.get('/hrms/employees', headers=admin)
    assert employees.status_code == 200, employees.text
    options = app.get('/hrms/employees/form-options', headers=admin).json()
    previous = next((e for e in employees.json() if e['work_email'] == 'hrms.boundary.check@newtuple.com'), None)
    payload = dict(first_name='Architecture', last_name='Verification', work_email='hrms.boundary.check@newtuple.com',
                   department=previous['department'] if previous else options['departments'][0], designation=previous['designation'] if previous else options['designations'][0],
                   role='hrms_employee', date_joined='2026-09-28', idempotency_key='boundary-smoke-employee-v1')
    created = app.post('/hrms/employees', headers=admin, json=payload)
    assert created.status_code == 201, created.text
    case_id = created.json()['onboarding_entity_id']
    assert created.json()['onboarding_task_count'] == 8, created.text
    repeat = app.post('/hrms/employees', headers=admin, json=payload)
    assert repeat.status_code == 201 and repeat.json()['idempotent'], repeat.text
    assert repeat.json()['employee']['entity_id'] == created.json()['employee']['entity_id']
    conflict = app.post('/hrms/employees', headers=admin, json={**payload, 'last_name': 'Changed'})
    assert conflict.status_code == 409, conflict.text
    cases = app.get('/hrms/onboarding', headers=admin)
    assert cases.status_code == 200, cases.text
    case = next(c for c in cases.json() if c['entity_id'] == case_id)
    if case['completed_steps'] == 0:
        denied = app.post(f'/hrms/onboarding/{case_id}/steps/3/complete', headers=admin)
        assert denied.status_code == 409, denied.text
        denied = app.post(f'/hrms/onboarding/{case_id}/complete', headers=admin)
        assert denied.status_code == 409, denied.text
    for sequence in range(1, 9):
        result = app.post(f'/hrms/onboarding/{case_id}/steps/{sequence}/complete', headers=admin)
        assert result.status_code == 200, result.text
    result = app.post(f'/hrms/onboarding/{case_id}/complete', headers=admin)
    assert result.status_code == 200 and result.json()['state'] == 'completed', result.text
    assert app.post(f'/entities/{case_id}/transitions', headers=admin, json={'trigger': 'complete'}).status_code == 403
    assert app.patch('/tasks/anything', headers=admin, json={'status': 'COMPLETED'}).status_code == 403
    platform = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                              os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    rows = platform.records('HRMS.Employee', ['employee_code','work_email','platform_user_id','reports_to_employee_code'])
    employee = next(r for r in rows if r['data'].get('work_email') == 'kavya.menon@newtuple.com')
    manager = next(r for r in rows if r['data'].get('employee_code') == employee['data']['reports_to_employee_code'])
    # The existing demo login may have HR roles granted during user review. Use an isolated
    # employee-only fixture instead of altering any existing user's permissions.
    fixture_email = 'hrms.boundary.employee@newtuple.com'
    users = platform.users()
    fixture = next((u for u in users if u['email'] == fixture_email), None)
    if not fixture:
        registered = platform.request('POST', '/auth/register', json={
            'email': fixture_email, 'password': os.environ['HRMS_DEMO_EMPLOYEE_PASSWORD'],
            'full_name': 'Boundary Test Employee', 'role': 'hrms_employee'})
        assert registered['organization_id'] == os.environ['HRMS_ORGANIZATION_ID']
        fixture = {'id': registered['user_id'], 'status': 'pending'}
    if fixture['status'] == 'pending':
        platform.call('POST', f"/users/{fixture['id']}/approve")
    employee_role = next(r for r in platform.call('GET', '/roles') if r['name'] == 'hrms_employee')
    platform.call('PUT', f"/roles/users/{fixture['id']}/role", json={'role_id': employee_role['id']})
    if not any(r['data'].get('work_email') == fixture_email for r in rows):
        platform.create_record('HRMS.Employee', dict(first_name='Boundary', last_name='Test Employee',
            work_email=fixture_email, employee_code='BOUNDARY-EMP', department=payload['department'],
            designation=payload['designation'], employment_status='active', hrms_role='hrms_employee',
            platform_user_id=fixture['id'], reports_to_employee_code=manager['data']['employee_code']), fixture['id'])
    user_login = app.post('/auth/login', json={'email': fixture_email, 'password': os.environ['HRMS_DEMO_EMPLOYEE_PASSWORD']})
    assert user_login.status_code == 200, user_login.text
    user_headers = {'Authorization': 'Bearer ' + user_login.json()['access_token']}
    assert app.get('/hrms/employees', headers=user_headers).status_code == 403
    assert app.post('/hrms/employees', headers=user_headers, json=payload).status_code == 403
    assert app.get('/hrms/onboarding', headers=user_headers).status_code == 200
    manager_login = app.post('/auth/login', json={'email': manager['data']['work_email'], 'password': os.environ['HRMS_DEMO_MANAGER_PASSWORD']})
    assert manager_login.status_code == 200, manager_login.text
    manager_headers = {'Authorization': 'Bearer ' + manager_login.json()['access_token']}
    leave = app.post('/hrms/leave-requests', headers=user_headers, json=dict(
        start_date='2041-09-21', end_date='2041-09-22', leave_type='annual', reason='Local boundary verification',
        idempotency_key='boundary-smoke-leave-v1'))
    assert leave.status_code == 201, leave.text
    entity_id = leave.json()['entity_id']
    denied = app.post(f'/hrms/leave-requests/{entity_id}/actions', headers=user_headers,
                      json={'trigger':'approve', 'idempotency_key':'boundary-smoke-decision-self'})
    assert denied.status_code == 403, denied.text
    approved = app.post(f'/hrms/leave-requests/{entity_id}/actions', headers=manager_headers,
                        json={'trigger':'approve','idempotency_key':'boundary-smoke-decision-v1'})
    assert approved.status_code == 200, approved.text
    assert platform.states('hrms_leaverequest')[entity_id] == 'approved'
    assert platform.states('hrms_onboardingcase')[case_id] == 'completed'
    routes = httpx.get('http://platform-api:8000/openapi.json', timeout=30).json()['paths']
    assert not any('/hrms/' in route for route in routes)
    print('PASS: directory, role denial, employee creation/retry/conflict, onboarding dependencies/completion, leave approval, native bypass denial, core has no HRMS routes')
    print('Local fixture retained: Architecture Verification (hrms.boundary.check@newtuple.com)')


if __name__ == '__main__':
    main()
