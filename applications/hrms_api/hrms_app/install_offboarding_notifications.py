"""Install a private native delivery workflow without changing platform code."""
from .errors import AppError
from .offboarding_notifications import ENTITY, FIELDS, definition


def install(api):
    try:
        api.call('GET', '/entity-types/' + ENTITY)
    except AppError as exc:
        if exc.status != 404:
            raise
        api.call('POST', '/entity-types', json={'organization_id': api.org, 'name': ENTITY,
                 'description': 'Private durable offboarding notification envelopes',
                 'schema_definition': {'fields': FIELDS, 'identifier_template': 'EXIT-MAIL-{{seq}}'}, 'version': 1})
    rows = api.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items']
    workflows = [w for w in rows if w['entity_type'] == ENTITY and w['is_active']]
    if len(workflows) > 1:
        raise AppError(409, 'Multiple offboarding notification workflows')
    if workflows:
        workflow = workflows[0]
    else:
        drafts = api.call('GET', '/workflow-state-machines', params={'scope': 'draft'})['draft_items']
        matching = [d for d in drafts if d['name'] == 'Offboarding notifications']
        if len(matching) > 1:
            raise AppError(409, 'Multiple notification workflow drafts')
        draft = matching[0] if matching else api.call('POST', '/workflow-state-machines/draft', json={'name': 'Offboarding notifications'})
        graph = definition()
        graph['machine_key'] = draft['machine_name']
        if matching:
            existing = api.call('GET', '/workflow-state-machines/' + draft['id']).get('definition')
            if existing:
                from copy import deepcopy
                existing = deepcopy(existing)
                for transition in existing.get('transitions', []):
                    if 'from_state' in transition:
                        transition['from'] = transition.pop('from_state')
                if existing != graph:
                    raise AppError(409, 'Review the edited notification workflow draft before publishing')
        workflow = api.call('POST', '/workflow-state-machines/' + draft['id'] + '/publish',
                            json={'definition': graph})['state_machine']
    service = next(r for r in api.call('GET', '/roles') if r['name'] == 'hrms_application_service')
    role = api.call('GET', '/roles/' + service['id'])
    permissions = {p['permission_key'] for p in role['permissions']}
    entity_permissions = [{k: v for k, v in p.items() if k not in {'id', 'role_id', 'organization_id'}}
                          for p in role['entity_permissions'] if p['entity_type'] != ENTITY]
    entity_permissions += [dict(entity_type=ENTITY, action=a, allowed=True) for a in ('view', 'create', 'edit')]
    fields = [{k: p[k] for k in ('entity_type', 'field_name', 'can_view', 'can_edit', 'mask_value')}
              for p in role['field_permissions'] if p['entity_type'] != ENTITY]
    fields += [dict(entity_type=ENTITY, field_name=f['field'], can_view=True, can_edit=True, mask_value=False)
               for f in [*FIELDS, {'field': 'identifier'}]]
    workflows_grants = [{'machine_name': p['machine_name']} for p in role['workflow_permissions']]
    if workflow['machine_name'] not in {p['machine_name'] for p in workflows_grants}:
        workflows_grants.append({'machine_name': workflow['machine_name']})
    api.call('PUT', '/roles/' + role['id'], json={
        'permissions': [{'permission_key': k} for k in sorted(permissions | {'entity_record:read', 'email_template:read'})],
        'entity_permissions': entity_permissions, 'field_permissions': fields, 'workflow_permissions': workflows_grants,
    })
    # Native generic views must not expose employee feedback to other roles.
    # Apply only this privacy ceiling, preserving all unrelated role grants.
    from .offboarding_checklist import CHECKLIST
    private = {f['field'] for f in CHECKLIST['Employee Feedback & Experience']} | {'checklist_submission_history'}
    for summary in api.call('GET', '/roles'):
        if summary['name'] in {'superadmin', 'hrms_hr_full', 'hrms_application_service'}:
            continue
        other = api.call('GET', '/roles/' + summary['id'])
        existing = [{k: p[k] for k in ('entity_type', 'field_name', 'can_view', 'can_edit', 'mask_value')}
                    for p in other['field_permissions']]
        fields = [p for p in existing if p['entity_type'] != 'HRMS.Offboarding' or p['field_name'] not in private]
        fields += [dict(entity_type='HRMS.Offboarding', field_name=k, can_view=False, can_edit=False, mask_value=False) for k in sorted(private)]
        if sorted(fields, key=lambda p: (p['entity_type'], p['field_name'])) != sorted(existing, key=lambda p: (p['entity_type'], p['field_name'])):
            api.call('PUT', '/roles/' + other['id'], json={'field_permissions': fields})
    return workflow


if __name__ == '__main__':
    import os
    from .platform import PlatformClient
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        # Deployment only repairs runtime grants after the reviewed native
        # package has created the entity. Never enable this feature implicitly.
        try:
            api.call('GET', '/entity-types/' + ENTITY)
        except AppError as exc:
            if exc.status != 404:
                raise
            print('Offboarding notification configuration is not installed; unchanged')
        else:
            install(api)
            print('Native offboarding notification runtime grants verified')
    finally:
        api.close()
