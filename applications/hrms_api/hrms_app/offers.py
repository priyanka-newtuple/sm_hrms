"""Narrow native offer creation surface, always using the caller's token."""
from .errors import AppError
from .policy import require, capabilities


def offer_metadata_access(actor, path):
    """Native form dependencies for HR creators; never grant Settings writes."""
    if 'cockpit:view' not in capabilities(actor) or not {
        'entity_record:write', 'workflow:read', 'form:read'
    }.issubset(actor.permissions):
        return False
    if any(part in path for part in ('..', '%', '\\', '//')):
        return False
    return (path == 'entity-types' or path.startswith('entity-types/') or
            path == 'forms/config' or path.startswith('forms/config/') or
            path == 'config/picklists' or path.startswith('config/picklists/') or
            (path.startswith('workflow-state-machines/') and len(path.split('/')) == 2))


def is_offer(name):
    return str(name).lower().replace('.', '').replace('_', '') == 'hrmsoffer'


def offer_workflow_rows(platform, actor):
    """Offer boards read native enrollments under the human's record permissions."""
    if 'cockpit:view' not in capabilities(actor) or 'workflow:read' not in actor.permissions:
        return []
    read = lambda path, **kwargs: platform.request('GET', path, token=actor.token, **kwargs)
    catalog = read('/workflow-state-machines', params={'scope': 'published'})
    offers = {w['machine_name']: w for w in catalog.get('published_items', []) if is_offer(w.get('entity_type')) and w.get('is_active')}
    rows = []
    for machine, workflow in offers.items():
        offset = 0
        while True:
            page = read('/workflow-enrollments', params={'machine_name': machine, 'limit': 200, 'offset': offset, 'fields': 'identifier'})
            if page.get('scan_truncated'):
                raise AppError(502, 'Offer results are incomplete; refine your workflow permissions')
            for item in page.get('items', []):
                if item.get('organization_id') != actor.organization_id:
                    raise AppError(502, 'Offer result belongs to another organization')
                if not is_offer(item.get('entity_type')) or item.get('machine_name') != machine:
                    continue
                record = workflow if item['machine_version'] == workflow['version'] else read(f"/workflow-state-machines/{machine}/{item['machine_version']}")
                definition = record['definition']
                states = [dict(name=s['name'], label=s['name'], terminal='terminal' in s.get('tags', [])) for s in definition['states']]
                state = next((s for s in states if s['name'] == item['current_state']), {})
                identifier = item.get('summary_fields', {}).get('identifier') or item.get('display_name') or item['entity_id']
                rows.append(dict(entity_id=item['entity_id'], entity_type=item['entity_type'], title=identifier,
                    identifier=identifier, current_state=item['current_state'], state_label=item['current_state'],
                    is_terminal=state.get('terminal', False), workflow_label=record['name'], owner_name='',
                    next_action='', progress='', due_date=item.get('due_date'), leave=None, leave_view=None,
                    workflow_configuration=dict(name=record['name'], version=record['version'], machine_name=machine, states=states, transitions=[])))
            if not page.get('has_more'):
                break
            if not page.get('items'):
                raise AppError(502, 'Offer results are incomplete')
            offset += len(page['items'])
    return rows


def authorize_offer_request(platform, actor, path, payload):
    require(actor, 'cockpit:view')
    if not isinstance(payload, dict):
        raise AppError(400, 'An offer request body is required')
    if any(str(payload[k]) != actor.organization_id for k in ('organization_id', 'org_id') if k in payload):
        raise AppError(403, 'Offers are restricted to your organization')
    def read(route):
        return platform.request('GET', route, token=actor.token)
    if path == 'entity-records':
        if not payload.get('entity_type_id'):
            raise AppError(403, 'This action requires an offer entity type')
        types = read('/entity-types').get('items', [])
        matching = [t for t in types if str(t.get('entity_type_id') or t.get('id')) == str(payload.get('entity_type_id')) and is_offer(t.get('name'))]
        if not matching:
            raise AppError(403, 'This action can only create offers')
        return
    parts = path.split('/')
    if len(parts) != 3 or parts[0] != 'workflow-state-machines' or parts[2] != 'enrollments':
        raise AppError(403, 'Unsupported offer action')
    if not payload.get('entity_id'):
        raise AppError(403, 'This action requires an offer record')
    workflow = read(f'/workflow-state-machines/{parts[1]}/active')
    if not is_offer(workflow.get('entity_type')) or not workflow.get('is_active'):
        raise AppError(403, 'Select an active offer workflow')
    entity_id = payload.get('entity_id', '')
    from uuid import UUID
    try:
        UUID(str(entity_id))
    except ValueError as exc:
        raise AppError(400, 'Invalid offer record') from exc
    record = read(f'/entity-records/{entity_id}')
    types = read('/entity-types').get('items', [])
    if record.get('organization_id') != actor.organization_id or not any(
        str(t.get('entity_type_id') or t.get('id')) == str(record.get('entity_type_id')) and is_offer(t.get('name')) for t in types
    ):
        raise AppError(403, 'Only offers in your organization can be enrolled')
