"""Read-only post-deployment verification of native HRMS configuration."""
import os

import httpx

from .form_config import configured_form
from .platform import PlatformClient


def verify_workflow_methods(methods, workflows):
    # Native methods may be reusable across entities (empty entity_types).
    # Validate the actual workflow links instead of rejecting shared methods.
    method_ids = {m['method_id'] for m in methods}
    for workflow in workflows:
        for state in workflow['definition']['states']:
            refs = state.get('method_refs') or []
            assert refs, 'Workflow state without native form'
            assert all(ref['method_id'] in method_ids for ref in refs), 'Workflow references a missing native form'


def main():
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        methods = api.call('GET', '/method-library/methods', params={'limit': 200})['items']
        assert methods, 'Native Forms are missing'
        workflows = [w for w in api.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items'] if w['is_active']]
        verify_workflow_methods(methods, workflows)
        from .onboarding_bindings import resolve
        resolve(api)
        assert any(r['name'] == 'hrms_onboarding_employee' for r in api.call('GET', '/roles')), 'Restricted onboarding role missing'
        employee = configured_form(api, 'HRMS.Employee')
        fields = {f['field']: f for f in employee['fields']}
        project = configured_form(api, 'HRMS.Project')
        assert all(f['type'] == 'float' for f in project['fields'] if f['field'] in {'billing_rate', 'budget_amount', 'planned_hours'}), 'Project decimal field mismatch'
        with httpx.Client(base_url='http://hrms-app:8000/v1/api', timeout=60,
                          headers={'Authorization': 'Bearer ' + api.service_token()}) as client:
            response = client.get('/hrms/capabilities')
            response.raise_for_status()
            assert 'platform:configure' in response.json()['capabilities'], 'Super Admin configuration access missing'
            if os.environ.get('HRMS_EMAIL_MODE') == 'capture' and os.environ.get('HRMS_UAT_INBOX_ENABLED') == 'true':
                status = client.get('/hrms/uat-mail/status')
                status.raise_for_status()
                assert status.json().get('enabled'), 'Super Admin UAT inbox access missing'
                client.get('/hrms/uat-mail/messages').raise_for_status()
                print('UAT inbox verification passed: admin access and Mailpit connectivity')
            response = client.get('/hrms/employees/form-options')
            response.raise_for_status()
            options = response.json()
            for key in ('department', 'designation'):
                assert options[key + 's'] == (fields[key].get('enum_values') or []), 'Dropdown differs from native form'
            for path in ('/hrms/employees', '/hrms/projects', '/hrms/user-approvals'):
                client.get(path).raise_for_status()
        print(f'Native HRMS verification passed: {len(methods)} forms, {len(workflows)} workflows, picklists and Super Admin access')
    finally:
        api.close()


if __name__ == '__main__':
    main()
