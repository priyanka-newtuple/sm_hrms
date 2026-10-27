"""Install HRMS configuration using public APIs. Run as a separate bootstrap job."""
import os

from .catalog import PACKS
from .cockpit_catalog import TYPES as COCKPIT_TYPES
from .errors import AppError
from .field_access import RUNTIME_TYPES, configured_fields, configured_transitions, grant, sync_service_access
from .form_config import has_method_blocks
from .install_employee_picklists import install_employee_picklists
from .install_project_roles import install_project_role_picklist
from .platform import PlatformClient
from .permission_migration import INITIAL_ROLE_GRANTS, migrate_native_permissions, migration_complete
from .project_catalog import TYPES as PROJECT_TYPES
from .provisioning import ensure_tenant_administrator
from .wfh_catalog import TYPES as WFH_TYPES
from .asset_catalog import ASSET
from .install_local_mail import install_local_mail
from .install_assets import install_asset_form, install_asset_permissions


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
        if pack.entity_type in {"HRMS.OnboardingCase", "HRMS.OnboardingStep"}:
            continue  # Retired; preserve historical records, never install new legacy flows.
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
        asset_method = install_asset_form(api, pack) if pack.entity_type == ASSET else None
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
                definition = pack.workflow_definition()
                if asset_method:
                    # Native blocks supply the schema, including live picklist bindings.
                    definition['entity_schema']['fields'] = []
                    for state in definition['states']:
                        state['method_refs'] = [{'method_id': asset_method}]
                published_row = api.call('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': definition})['state_machine']
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
            elif pack.entity_type == 'HRMS.LeaveRequest':
                current = api.call('GET', f"/workflow-state-machines/{matching[0]['id']}")
                definition = current['definition']
                if not any(t.get('from', t.get('from_state')) == 'approved' and t['trigger'] == 'cancel'
                           for t in definition['transitions']):
                    # Approved leave can be cancelled before it starts, so approved stops being terminal.
                    # Preserve configured guards, forms and transitions; publish an additive version.
                    for state in definition['states']:
                        if state['name'] == 'approved':
                            state['tags'] = [tag for tag in state.get('tags', []) if tag != 'terminal']
                    definition['transitions'].append({'key': 'approved_to_cancelled', 'trigger': 'cancel',
                        'label': 'Cancel', 'from': 'approved', 'to_state': 'cancelled'})
                    draft = api.call('POST', f"/workflow-state-machines/{matching[0]['machine_name']}/draft", json={'definition': definition})
                    matching = [api.call('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': definition})['state_machine']]
            if pack.entity_type == 'HRMS.Project':
                current = api.call('GET', f"/workflow-state-machines/{matching[0]['id']}")
                definition = current['definition']
                approvals = [t for t in definition['transitions']
                             if t['from'] == 'draft' and t['trigger'] == 'approve'
                             and t['to_state'] == 'planned']
                if approvals:
                    # Upgrade the old default without replacing tenant guards or other transitions.
                    for transition in approvals:
                        transition['to_state'] = 'active'
                        transition['key'] = 'draft_to_active'
                    # Planned was only reachable through approval in the old default.
                    # Keep it only if tenant configuration supplies another entry path.
                    if not any(t['to_state'] == 'planned' and t['from'] != 'planned'
                               for t in definition['transitions']):
                        definition['states'] = [state for state in definition['states'] if state['name'] != 'planned']
                        definition['transitions'] = [t for t in definition['transitions'] if t['from'] != 'planned']
                    draft = api.call('POST', f"/workflow-state-machines/{matching[0]['machine_name']}/draft", json={'definition': definition})
                    matching = [api.call('POST', f"/workflow-state-machines/{draft['id']}/publish", json={'definition': definition})['state_machine']]
            machines[pack.machine_name] = matching[0]['machine_name']

    install_project_role_picklist(api)
    install_employee_picklists(api)

    roles = api.call('GET', '/roles')
    by_name = {r['name']: r for r in roles}
    migrated = migration_complete(os.environ['HRMS_APP_DATABASE_URL'], org)
    for name in ([] if migrated else INITIAL_ROLE_GRANTS):
        if not name.startswith('hrms_'):
            continue
        if name not in by_name:
            by_name[name] = api.call('POST', '/roles', json={
                'name': name, 'display_name': name.removeprefix('hrms_').replace('_', ' ').title(),
                'description': 'HRMS role; permissions are configured in native Roles & Permissions',
                'permissions': [], 'entity_permissions': [], 'workflow_permissions': [], 'transition_permissions': []})
        # Existing tenant role customizations are left intact. The gateway is the only browser API surface.

    migrate_native_permissions(api, os.environ['HRMS_APP_DATABASE_URL'])
    install_asset_permissions(api, os.environ['HRMS_APP_DATABASE_URL'])
    install_local_mail(api)

    service_name = 'hrms_application_service'
    runtime_packs = [p for p in PACKS if p.entity_type in RUNTIME_TYPES]
    role_spec = dict(name=service_name, display_name='HRMS Application Service',
        description='Internal API client for HRMS; never assign to a human user',
        permissions=[{'permission_key': key} for key in ['entity_record:write', 'workflow:read', 'workflow:write',
            'file:read', 'file:write', 'user:read', 'user:write', 'role:read', 'form:read', 'integration:read',
            'field_library:read', 'method_library:read']],
        entity_permissions=[{'entity_type': p.entity_type, 'action': action}
                            for p in runtime_packs for action in ['view', 'create', 'edit']],
        # Fields added to the forms in Settings too, so a redeploy never takes their access away.
        field_permissions=[grant(p.entity_type, name) for p in runtime_packs
                           for name in dict.fromkeys([*(f['field'] for f in (*p.fields, marker)),
                                                      *configured_fields(api, p.entity_type)])],
        workflow_permissions=[{'machine_name': machines[p.machine_name]} for p in runtime_packs if p.states],
        # Steps added to the workflows in Settings too, so a redeploy never takes their access away.
        transition_permissions=[{'machine_name': machine, 'transition_key': key} for machine, key in dict.fromkeys([
            *((machines[p.machine_name], f'{source}_to_{target}') for p in runtime_packs for source, _, target in p.transitions),
            *(step for p in runtime_packs if p.states for step in configured_transitions(api, p.entity_type))])])
    # Older project instances remain pinned to the previous published workflow.
    project_pack = next(p for p in runtime_packs if p.entity_type == 'HRMS.Project')
    granted = {(t['machine_name'], t['transition_key']) for t in role_spec['transition_permissions']}
    role_spec['transition_permissions'].extend(
        {'machine_name': machines[project_pack.machine_name], 'transition_key': key}
        for key in ('draft_to_planned', 'planned_to_active', 'planned_to_completed')
        if (machines[project_pack.machine_name], key) not in granted)
    role = by_name.get(service_name)
    if role:
        api.call('PUT', f"/roles/{role['id']}", json=role_spec)
    else:
        role = api.call('POST', '/roles', json=role_spec)
    sync_service_access(api, lambda method, path, **kwargs: api.call(method, '/' + path, **kwargs))
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
    from .install_offboarding import install as install_offboarding
    install_offboarding(api, os.environ['HRMS_APP_DATABASE_URL'])
    from .install_asset_bulk import install as install_asset_bulk
    install_asset_bulk(api)
    # Verify real authentication and tenant context before reporting installation success.
    runtime = PlatformClient(os.environ['PLATFORM_API_URL'], org, email, os.environ['HRMS_SERVICE_PASSWORD'])
    runtime.service_token()
    runtime.close()
    api.close()
    print('HRMS API product configuration and dedicated service identity are ready')


if __name__ == '__main__':
    install()

