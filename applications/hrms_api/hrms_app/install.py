"""Install HRMS configuration using public APIs. Run as a separate bootstrap job."""
import os

from .catalog import PACKS
from .cockpit_catalog import TYPES as COCKPIT_TYPES
from .errors import AppError
from .form_config import has_method_blocks
from .install_project_roles import install_project_role_picklist
from .platform import PlatformClient
from .policy import ROLE_CAPABILITIES
from .project_catalog import TYPES as PROJECT_TYPES
from .provisioning import ensure_tenant_administrator
from .wfh_catalog import TYPES as WFH_TYPES


def install():
    org = os.environ['HRMS_ORGANIZATION_ID']
    api = PlatformClient(os.environ['PLATFORM_API_URL'], org,
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    organization = ensure_tenant_administrator(api)
    domain = os.environ.get('HRMS_WORK_EMAIL_DOMAIN', 'newtuple.com')
    if organization.get('domain') != domain:
        # Organization domains are platform administration, only the installer gets this credential.
        root = api.request('POST', '/auth/login', json={
            'email': os.environ['HRMS_PLATFORM_OWNER_EMAIL'], 'password': os.environ['HRMS_PLATFORM_OWNER_PASSWORD']})
        api.request('PUT', f'/organizations/{org}', token=root['access_token'], json={'domain': domain})

    marker = {'field': 'hrms_operation_key', 'type': 'string'}
    machines = {}
    for pack in PACKS:
        # Existing forms/workflows remain version-pinned. The operation marker is entity metadata.
        desired = pack.entity_request(org)
        desired['schema_definition']['fields'].append(marker)
        try:
            existing = api.call('GET', f'/entity-types/{pack.entity_type}')
        except AppError as exc:
            if exc.status != 404:
                raise
            existing = api.call('POST', '/entity-types', json=desired)
        else:
            schema = existing['schema_definition']
            fields = {field['field']: field for field in schema.get('fields', [])}
            additions = [field for field in desired['schema_definition']['fields'] if field['field'] not in fields]
            if additions:
                api.call('PUT', f'/entity-types/{pack.entity_type}', json={
                    'schema_definition': {**schema, 'fields': [*schema.get('fields', []), *additions]}})
        forms = api.call('GET', '/forms/config', params={'entity_type': pack.entity_type})['items']
        # A type moved onto method blocks is configured there; never recreate its legacy Form.
        if not any(f['schema_key'] == pack.schema_key for f in forms) and not has_method_blocks(api, pack.entity_type):
            api.call('POST', '/forms/config', json=pack.form_request())
        if pack.states:
            published = api.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items']
            matching = [w for w in published if w['entity_type'] == pack.entity_type and w['is_active']]
            if len(matching) > 1:
                raise RuntimeError(f'Multiple active workflows for {pack.entity_type}; choose one before installing')
            if not matching:
                draft = api.call('POST', '/workflow-state-machines/draft', json={'name': pack.label})
                published_row = api.call('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': pack.workflow_definition()})['state_machine']
                matching = [published_row]
            elif pack.entity_type == 'HRMS.ProjectChange':
                current = api.call('GET', f"/workflow-state-machines/{matching[0]['id']}")
                definition = current['definition']
                if not any(t['trigger'] == 'withdraw' for t in definition['transitions']):
                    # Preserve configured guards, forms and transitions; publish an additive version.
                    definition['transitions'].append({'key': 'pending_to_draft', 'trigger': 'withdraw',
                        'label': 'Withdraw', 'from': 'pending', 'to_state': 'draft'})
                    draft = api.call('POST', f"/workflow-state-machines/{matching[0]['machine_name']}/draft", json={'definition': definition})
                    matching = [api.call('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': definition})['state_machine']]
            machines[pack.machine_name] = matching[0]['machine_name']

    install_project_role_picklist(api)

    roles = api.call('GET', '/roles')
    by_name = {r['name']: r for r in roles}
    for name in ROLE_CAPABILITIES:
        if not name.startswith('hrms_'):
            continue
        if name not in by_name:
            by_name[name] = api.call('POST', '/roles', json={
                'name': name, 'display_name': name.removeprefix('hrms_').replace('_', ' ').title(),
                'description': 'HRMS product role; capabilities are enforced by the HRMS application',
                'permissions': [], 'entity_permissions': [], 'workflow_permissions': [], 'transition_permissions': []})
        # Existing tenant role customizations are left intact. The gateway is the only browser API surface.

    service_name = 'hrms_application_service'
    runtime_packs = [p for p in PACKS if p.entity_type in {*PROJECT_TYPES, *COCKPIT_TYPES, *WFH_TYPES,
        'HRMS.Employee', 'HRMS.OnboardingCase', 'HRMS.OnboardingStep', 'HRMS.LeaveRequest',
        'HRMS.PerformanceCycle', 'HRMS.PerformanceReview', 'HRMS.PerformanceGoal', 'HRMS.ProjectFeedback'}]
    role_spec = dict(name=service_name, display_name='HRMS Application Service',
        description='Internal API client for HRMS; never assign to a human user',
        permissions=[{'permission_key': key} for key in ['entity_record:write', 'workflow:read', 'workflow:write',
            'user:read', 'user:write', 'role:read', 'form:read', 'integration:read',
            'field_library:read', 'method_library:read']],
        entity_permissions=[{'entity_type': p.entity_type, 'action': action}
                            for p in runtime_packs for action in ['view', 'create', 'edit']],
        field_permissions=[{'entity_type': p.entity_type, 'field_name': field['field'],
                            'can_view': True, 'can_edit': True, 'mask_value': False}
                           for p in runtime_packs for field in [*p.fields, marker]],
        workflow_permissions=[{'machine_name': machines[p.machine_name]} for p in runtime_packs if p.states],
        transition_permissions=[{'machine_name': machines[p.machine_name], 'transition_key': f'{source}_to_{target}'}
                                for p in runtime_packs for source, _, target in p.transitions])
    role = by_name.get(service_name)
    if role:
        api.call('PUT', f"/roles/{role['id']}", json=role_spec)
    else:
        role = api.call('POST', '/roles', json=role_spec)
    email = os.environ['HRMS_SERVICE_EMAIL']
    user = next((u for u in api.users() if u['email'] == email), None)
    if user is None:
        registration = api.request('POST', '/auth/register', json={
            'email': email, 'password': os.environ['HRMS_SERVICE_PASSWORD'],
            'full_name': 'HRMS Application Service', 'role': service_name})
        if registration.get('organization_id') != org or registration.get('approval_type') != 'pending_org_admin':
            raise RuntimeError('Service registration did not return the expected organization and status')
        user = {'id': registration['user_id'], 'status': 'pending'}
    if user['status'] == 'pending':
        api.call('POST', f"/users/{user['id']}/approve")
    api.call('PUT', f"/roles/users/{user['id']}/role", json={'role_id': role['id']})
    # Verify real authentication and tenant context before reporting installation success.
    runtime = PlatformClient(os.environ['PLATFORM_API_URL'], org, email, os.environ['HRMS_SERVICE_PASSWORD'])
    runtime.service_token()
    runtime.close()
    api.close()
    print('HRMS API product configuration and dedicated service identity are ready')


if __name__ == '__main__':
    install()

