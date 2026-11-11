"""Create the missing restricted native role; preserve existing tenant role settings."""
import os

from .errors import AppError
from .onboarding_bindings import resolve
from .platform import PlatformClient


def install(api):
    bindings = resolve(api)
    workflows = api.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items']
    workflows = [w for w in workflows if w['entity_type'] == 'HRMS.Employee' and w['is_active']]
    profile = bindings['HRMS_EMPLOYEE_PROFILE_FORM_ID']
    candidates = [w for w in workflows if any(r['method_id'] == profile for s in w['definition']['states'] for r in s.get('method_refs', []))]
    if len(candidates) != 1:
        raise AppError(409, 'Configure one active employee onboarding workflow')
    workflow = candidates[0]
    refs = {r['method_id'] for s in workflow['definition']['states'] for r in s.get('method_refs', [])}
    # Account Approval is optional: current workflows create the login on the hand-over to the employee.
    required = {v for k, v in bindings.items() if k != 'HRMS_EMPLOYEE_APPROVAL_FORM_ID'}
    if not required <= refs:
        raise AppError(409, 'Published onboarding workflow is missing lifecycle forms')
    roles = api.call('GET', '/roles')
    existing = next((r for r in roles if r['name'] == 'hrms_onboarding_employee'), None)
    if existing:
        role = api.call('GET', f"/roles/{existing['id']}")
        permissions = {p['permission_key'] for p in role['permissions']}
        # Runtime transitions require this API permission in addition to the
        # configured workflow/transition grants. Preserve all tenant restrictions.
        if 'workflow:write' not in permissions:
            api.call('PUT', f"/roles/{existing['id']}", json={
                'permissions': [{'permission_key': key} for key in sorted(permissions | {'workflow:write'})],
            })
            print('Onboarding runtime transition permission repaired; tenant restrictions preserved')
        else:
            print('Existing native Onboarding Employee role preserved; lifecycle forms verified')
        profile_fields = [f for block in workflow['definition'].get('method_schemas', []) if block['method_id'] == profile for f in block['fields']]
        if any(f['field'] == 'permanent_same_as_current' for f in profile_fields):
            grants = list(role.get('field_permissions', []))
            existing_keys = {f['field_name'] for f in grants if f['entity_type'] == 'HRMS.Employee'}
            inherited = {f['field_name']: f for f in grants if f['entity_type'] == 'HRMS.Employee'}
            sources = {'emergency_contact_relationship': 'emergency_contact', 'emergency_contact_phone': 'emergency_contact',
                       'blood_group': 'date_of_birth', 'permanent_same_as_current': 'permanent_address_line_1',
                       'marksheets': 'onboarding_documents', 'experience_letters': 'onboarding_documents',
                       'aadhaar_card': 'onboarding_documents', 'pan_card': 'onboarding_documents'}
            published = {f['field'] for f in profile_fields}
            for key, source in sources.items():
                if key in published and key not in existing_keys and source in inherited:
                    grants.append({**inherited[source], 'field_name': key})
            if len(grants) != len(role.get('field_permissions', [])):
                api.call('PUT', f"/roles/{existing['id']}", json={'field_permissions': grants, 'permissions': [{'permission_key': key} for key in sorted(permissions | {'workflow:write', 'comment:read', 'comment:write'})]})
        return
    definition = workflow['definition']
    states = {s['name'] for s in definition['states'] if any(r['method_id'] == profile for r in s.get('method_refs', []))}
    fields = [f for block in definition.get('method_schemas', []) if block['method_id'] == profile for f in block['fields']]
    if not fields:
        raise AppError(409, 'Published employee profile fields are missing')
    editable = {f['field'] for f in fields if not f.get('read_only')}
    visible = {f['field'] for f in fields} | {'first_name', 'last_name', 'identifier', 'platform_user_id', 'hr_verification_notes', 'employment_status'}
    machine = workflow['machine_name']
    api.call('POST', '/roles', json={
        'name': 'hrms_onboarding_employee', 'display_name': 'Onboarding Employee',
        'description': 'Own employee onboarding through the restricted HRMS gateway.',
        'permissions': [{'permission_key': k} for k in ('workflow:read', 'workflow:write', 'entity_record:write', 'form:read', 'file:read', 'file:write', 'comment:read', 'comment:write')],
        'entity_permissions': [{'entity_type': 'HRMS.Employee', 'action': a, 'allowed': True} for a in ('view', 'edit')],
        'field_permissions': [{'entity_type': 'HRMS.Employee', 'field_name': f, 'can_view': True, 'can_edit': f in editable, 'mask_value': False} for f in sorted(visible)],
        'workflow_permissions': [{'machine_name': machine}],
        'transition_permissions': [{'machine_name': machine, 'transition_key': t['key']} for t in definition['transitions'] if t.get('from', t.get('from_state')) in states and not t['key'].startswith('cancel_onboarding_')],
    })
    print('Restricted native Onboarding Employee role created; lifecycle forms verified')


if __name__ == '__main__':
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'], os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        install(api)
    finally:
        api.close()
