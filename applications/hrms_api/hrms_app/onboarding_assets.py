"""Native Employee/Asset link adapter. Asset records remain assignment authority."""
import os
from .errors import AppError
from .asset_catalog import ASSET
from .policy import require

ASSET_FIELD = 'issued_asset_references'


def enabled():
    return bool(os.getenv('HRMS_ASSET_EMPLOYEE_RELATION'))


def existing_relations(platform, asset_id, employee_id):
    relation = os.getenv('HRMS_ASSET_EMPLOYEE_RELATION')
    if not relation:
        return []
    response = platform.call('GET', f'/entities/{asset_id}/relations', params={'direction':'out','relation_type':relation})
    if response['organization_id'] != platform.org:
        raise AppError(403, 'Asset relationship organization mismatch')
    rows = response['items']
    if any(r['to_entity_id'] != employee_id for r in rows):
        raise AppError(409, 'Asset is linked to another employee; reconcile the assignment first')
    return rows


def ensure_relation(platform, asset_id, employee_id):
    relation = os.getenv('HRMS_ASSET_EMPLOYEE_RELATION')
    if relation and not existing_relations(platform, asset_id, employee_id):
        platform.call('POST', f'/entities/{asset_id}/relations', json={
            'from_entity_id':asset_id,'to_entity_id':employee_id,'relation_type':relation})


def issued_assets(platform, employee_id):
    states = platform.states('hrms_asset')
    return [r for r in platform.records(ASSET, ['asset_tag','asset_name','serial_number','issued_employee_id','issued_date'])
            if r['organization_id'] == platform.org and r['data'].get('issued_employee_id') == employee_id
            and states.get(r['entity_id']) == 'issued']


def evidence(platform, employee_id):
    return '\n'.join(f"{r['data'].get('asset_tag') or r['entity_id']} | {r['data'].get('asset_name', '')} | {r['entity_id']}"
                     for r in issued_assets(platform, employee_id))


def context(platform, actor, employee_id, workflow_id):
    from .employee_work import employee_form, employee_work
    form = employee_form(platform, actor, employee_id, workflow_id)
    if not form.get('asset_section'):
        raise AppError(403, 'Asset issuance is not configured on this form')
    item = next((x for x in employee_work(platform, actor)
                 if x['entity_id']==employee_id and x['workflow_id']==workflow_id), None)
    return form, bool(item and item['actions'] and form.get('asset_field_editable'))


def board(assets, actor, employee_id, workflow_id):
    from .policy import capabilities
    form, actionable = context(assets.platform, actor, employee_id, workflow_id)
    can_issue = actionable and 'asset:manage' in capabilities(actor)
    assigned = issued_assets(assets.platform, employee_id)
    def summary(r):
        return {'id':r['entity_id'],'data':{k:v for k,v in r['data'].items()
                if k in {'asset_name','asset_tag','serial_number','issued_date'}},'state':'issued','actions':[]}
    inventory = assets.board(actor) if can_issue else {'items':[]}
    available = [{**r,'data':{k:v for k,v in r['data'].items() if k in {'asset_name','asset_tag','serial_number'}}}
                 for r in inventory['items'] if 'issue' in r['actions']]
    return {'assigned':list(map(summary,assigned)), 'available':available,'can_issue':can_issue,
            'legacy_references':form['values'].get(ASSET_FIELD)}


def issue(assets, actor, employee_id, workflow_id, asset_id, command):
    require(actor, 'asset:manage')
    _, actionable = context(assets.platform, actor, employee_id, workflow_id)
    if not actionable:
        raise AppError(403, 'Asset issuance is not available at your current workflow step')
    if command.action != 'issue' or command.data.get('issued_employee_id') != employee_id:
        raise AppError(422, 'Issue the asset to the employee on this onboarding record')
    result = assets.execute(actor, asset_id, command)
    # Evidence for the existing native transition is derived, never a second assignment store.
    assets.platform.request('PUT', f'/entity-records/{employee_id}', token=actor.token,
                            json={'data':{ASSET_FIELD:evidence(assets.platform,employee_id)}})
    return result
