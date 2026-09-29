"""Local-only, API-based demo provisioning. Passwords never go to stdout."""
import json
import os
from pathlib import Path
import secrets

import httpx

from hrms_app.platform import PlatformClient
from hrms_app.policy import ROLE_CAPABILITIES


ROLES = [
    ('employee', 'Employee', 'hrms_employee'),
    ('manager', 'Reporting Manager', 'hrms_manager'),
    ('hr-basic', 'HR Basic', 'hrms_hr_basic'),
    ('hr-full', 'HR Full', 'hrms_hr_full'),
    ('delivery-manager', 'Delivery Manager', 'hrms_delivery_manager'),
    ('project-manager', 'Project Manager', 'hrms_project_manager'),
    ('finance', 'Finance', 'hrms_finance'),
    ('office-admin', 'Office Admin', 'hrms_office_admin'),
    ('recruiter', 'Recruiter', 'hrms_recruiter'),
    ('performance-approver', 'Performance Approver', 'hrms_performance_approver'),
    ('viewer', 'Viewer', 'viewer'),
    ('admin', 'Admin', 'admin'),
    ('superadmin', 'Super Admin', 'superadmin'),
]


def main():
    if (os.environ.get('HRMS_LOCAL_SMOKE') != 'true'
            or os.environ['PLATFORM_API_URL'] != 'http://platform-api:8000/v1/api'
            or os.environ['HRMS_ORGANIZATION_ID'] != '11111111-1111-1111-1111-111111111111'):
        raise RuntimeError('Demo provisioning is restricted to the isolated local stack')
    path = Path('/demo/users.json')
    manifest = json.loads(path.read_text()) if path.exists() else {'accounts': []}

    def save():
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n')
        temporary.replace(path)

    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    native_roles = {r['name']: r for r in api.call('GET', '/roles')}
    users = {u['email']: u for u in api.users()}
    for slug, label, role in ROLES:
        email = f'demo.{slug}@newtuple.com'
        entry = next((a for a in manifest['accounts'] if a['email'] == email), None)
        if entry is None:
            if email in users:
                raise RuntimeError(f'Refusing to adopt existing account {email} without a local manifest')
            entry = dict(name=f'Demo {label}', email=email, role=role,
                         password=secrets.token_urlsafe(24), employee_code=f'DEMO-{slug.upper()}')
            manifest['accounts'].append(entry)
            save()
        user = users.get(email)
        if user is None:
            registration = api.request('POST', '/auth/register', json=dict(
                email=email, full_name=entry['name'], password=entry['password'], role='hrms_employee'))
            assert registration['organization_id'] == api.org
            user = dict(id=registration['user_id'], status='pending')
            entry['user_id'] = user['id']
            save()
        else:
            if entry.get('user_id') and entry['user_id'] != user['id']:
                raise RuntimeError(f'Identity changed for {email}; reconcile before continuing')
            # Verify the saved credential before changing an existing demo identity.
            api.request('POST', '/auth/login', json={'email': email, 'password': entry['password']}) if user['status'] == 'active' else None
            entry['user_id'] = user['id']
        if user['status'] == 'pending':
            api.call('POST', f"/users/{user['id']}/approve")
        elif user['status'] != 'active':
            raise RuntimeError(f'{email} is not active or pending; activation requires review')
        api.call('PUT', f"/roles/users/{user['id']}/role", json={'role_id': native_roles[role]['id']})
        save()

    employees = api.records('HRMS.Employee', ['work_email', 'platform_user_id', 'employee_code', 'hrms_operation_key'])
    for entry in manifest['accounts']:
        if entry['role'] == 'viewer':
            continue  # Viewer is a read-only observer, not a review participant.
        matches = [e for e in employees if e['data'].get('work_email') == entry['email']]
        assert len(matches) <= 1, 'Duplicate employee identity'
        marker = 'local-role-demo:' + entry['role']
        manager_code = ('DEMO-DELIVERY-MANAGER' if entry['role'] == 'hrms_manager'
                        else 'DEMO-SUPERADMIN' if entry['role'] == 'hrms_delivery_manager'
                        else None if entry['role'] == 'superadmin' else 'DEMO-MANAGER')
        values = dict(first_name='Demo', last_name=entry['name'].removeprefix('Demo '),
            employee_code=entry['employee_code'], work_email=entry['email'], platform_user_id=entry['user_id'],
            department='Demo', designation=entry['name'].removeprefix('Demo '), employment_status='active',
            hrms_role=entry['role'], reports_to_employee_code=manager_code, hrms_operation_key=marker)
        if matches:
            assert matches[0]['data'].get('hrms_operation_key') == marker, 'Existing non-demo employee must not be changed'
            entity_id = matches[0]['entity_id']
        else:
            entity_id = api.create_record('HRMS.Employee', values, entry['user_id'])['entity_id']
        entry['employee_entity_id'] = entity_id
        save()

    app = httpx.Client(base_url='http://hrms-app:8000/v1/api', timeout=120)
    for entry in manifest['accounts']:
        response = app.post('/auth/login', json={'email': entry['email'], 'password': entry['password']})
        assert response.status_code == 200, f"Login failed: {entry['email']} ({response.status_code})"
        headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
        actual_roles = api.call('GET', f"/roles/users/{entry['user_id']}/roles")
        assert {r['role_name'] for r in actual_roles if r['organization_id'] == api.org} == {entry['role']}
        expected = set(ROLE_CAPABILITIES[entry['role']])
        response = app.get('/hrms/capabilities', headers=headers)
        assert response.status_code == 200 and set(response.json()['capabilities']) == expected
        assert app.get('/hrms/employees', headers=headers).status_code == (200 if 'employee:read' in expected else 403)
        assert app.get('/hrms/performance/options', headers=headers).status_code == (200 if 'performance:manage' in expected else 403)
        assert app.post('/entity-records', headers=headers, json={}).status_code == 403
        assert app.get('/hrms/performance', headers=headers).status_code == 200
        entry['verified'] = True
        save()
        print(f"VERIFIED {entry['email']} | {entry['role']}", flush=True)
    print(f'{len(ROLES)} demo accounts ready. Credentials are in the local ignored users.json file.')


if __name__ == '__main__':
    main()
