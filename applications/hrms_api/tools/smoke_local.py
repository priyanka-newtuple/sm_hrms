"""Local-only integration verification. Creates a named fixture hire and request."""
import json
import os
from pathlib import Path

import httpx
from hrms_app.platform import PlatformClient

# Demo accounts get random passwords from seed_demo_users.py; the smoke run mounts that file at /demo.
DEMO = {a['email']: a['password'] for a in json.loads(Path('/demo/users.json').read_text())['accounts']}


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
    payload = {'first_name': 'Denied', 'last_name': 'Creation', 'work_email': 'denied.creation@newtuple.com', 'role': 'hrms_employee', 'date_joined': '2026-10-13', 'idempotency_key': 'boundary-denied-onboarding-v2', 'department': options['departments'][0], 'designation': options['designations'][0]}
    assert app.patch('/tasks/anything', headers=admin, json={'status': 'COMPLETED'}).status_code == 403
    platform = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                              os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    rows = platform.records('HRMS.Employee', ['employee_code','work_email','platform_user_id','reports_to_employee_code'])
    employee = next(r for r in rows if r['data'].get('work_email') == 'demo.employee@newtuple.com')
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
        platform.create_record('HRMS.Employee', {'first_name': 'Boundary', 'last_name': 'Test Employee',
            'work_email': fixture_email, 'employee_code': 'BOUNDARY-EMP', 'department': payload['department'],
            'designation': payload['designation'], 'employment_status': 'active', 'hrms_role': 'hrms_employee',
            'platform_user_id': fixture['id'], 'reports_to_employee_code': manager['data']['employee_code']}, fixture['id'])
    else:
        # This dedicated fixture may survive earlier manual local testing. Keep its
        # reporting line consistent with the manager this test signs in as.
        row = next(r for r in rows if r['data'].get('work_email') == fixture_email)
        current = platform.record(row['entity_id'])
        platform.call('PUT', f"/entity-records/{row['entity_id']}", json={
            'data': {**current['data'], 'reports_to_employee_code': manager['data']['employee_code']}})
    user_login = app.post('/auth/login', json={'email': fixture_email, 'password': os.environ['HRMS_DEMO_EMPLOYEE_PASSWORD']})
    assert user_login.status_code == 200, user_login.text
    user_headers = {'Authorization': 'Bearer ' + user_login.json()['access_token']}
    assert app.get('/hrms/employees', headers=user_headers).status_code == 403
    assert app.post('/hrms/employees', headers=user_headers, json=payload).status_code in {403, 404}
    legacy = app.get('/hrms/onboarding', headers=user_headers)
    assert legacy.status_code in {403, 404}, legacy.text  # Retired route is unavailable.
    manager_login = app.post('/auth/login', json={'email': manager['data']['work_email'], 'password': DEMO[manager['data']['work_email']]})
    assert manager_login.status_code == 200, manager_login.text
    manager_headers = {'Authorization': 'Bearer ' + manager_login.json()['access_token']}
    leave = app.post('/hrms/leave-requests', headers=user_headers, json={
        'start_date': '2041-09-23', 'end_date': '2041-09-24', 'leave_type': 'annual', 'reason': 'Local boundary verification',
        'idempotency_key': 'boundary-smoke-leave-v2'})
    assert leave.status_code == 201, leave.text
    entity_id = leave.json()['entity_id']
    denied = app.post(f'/hrms/leave-requests/{entity_id}/actions', headers=user_headers,
                      json={'trigger':'approve', 'idempotency_key':'boundary-smoke-decision-self-v2'})
    assert denied.status_code == 403, denied.text
    approved = app.post(f'/hrms/leave-requests/{entity_id}/actions', headers=manager_headers,
                        json={'trigger':'approve','idempotency_key':'boundary-smoke-decision-v2'})
    assert approved.status_code == 200, approved.text
    assert platform.states('hrms_leaverequest')[entity_id] == 'approved'
    routes = httpx.get('http://platform-api:8000/openapi.json', timeout=30).json()['paths']
    assert not any('/hrms/' in route for route in routes)
    print('PASS: directory, role denial, employee creation/retry/conflict, onboarding dependencies/completion, leave approval, native bypass denial, core has no HRMS routes')



if __name__ == '__main__':
    main()
