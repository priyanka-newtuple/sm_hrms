"""Relationship-scoped employee access, using public native APIs only.

Employees never receive broad native read access to confidential exit records.
This projection is a security ceiling; native methods further narrow the form.
"""
from .errors import AppError
from .offboarding_catalog import ENTITY, SECTIONS
from .offer_documents import digest

def employee_step(state):
    return any(a['kind']=='entity.assign_user' and a.get('config',{}).get('user_id')=='$entity.offboarding_employee_user_id' for a in state.get('on_state_actions',[]))
EMPLOYEE_FIELDS = {f['field'] for f in SECTIONS['Employee handover']}
PUBLIC_FIELDS = EMPLOYEE_FIELDS | {'identifier', 'confirmed_last_day', 'requested_last_day'}


class EmployeeOffboarding:
    def __init__(self, offboarding):
        self.offboarding = offboarding
        self.platform = offboarding.platform
        self.service = offboarding.service

    def own(self, actor):
        return self.service.own_employee(actor, self.service.employees())

    def context(self, actor, entity_id):
        own = self.own(actor)
        response = self.platform.call('GET', f'/entity-records/{entity_id}/with-states')
        record = response['entity']
        kind = self.platform.call('GET', '/entity-types/' + ENTITY)
        if (record['organization_id'] != actor.organization_id or record['entity_type_id'] != kind['entity_type_id']
                or record['data'].get('employee_id') != own['entity_id']):
            raise AppError(404, 'Offboarding record is not available')
        if len(response['states']) != 1:
            raise AppError(409, 'Offboarding enrollment needs review')
        enrollment = response['states'][0]
        workflow = self.platform.call('GET', f"/workflow-state-machines/{enrollment['workflow_id']}")
        if workflow['organization_id'] != actor.organization_id or workflow['entity_type'] != ENTITY:
            raise AppError(403, 'Invalid workflow scope')
        state = next(s for s in workflow['definition']['states'] if s['name'] == enrollment['current_state'])
        if 'initial' in state.get('tags', []) or state['name']=='Discarded':
            raise AppError(404, 'Offboarding has not been initiated')
        return record, enrollment, workflow, state

    def detail(self, actor, entity_id):
        record, enrollment, workflow, state = self.context(actor, entity_id)
        fields = [f for f in self.offboarding.fields(workflow, state['name']) if f['field'] in EMPLOYEE_FIELDS]
        editable = employee_step(state) and record.get('assignee_id') == actor.user_id
        values = {k:v for k,v in record['data'].items() if k in PUBLIC_FIELDS}
        transitions = [t for t in workflow['definition']['transitions'] if t.get('from') == state['name'] and t['trigger']=='submit_employee_handover']
        return dict(entity_id=entity_id, state=state['name'], values=values, values_hash=digest(values),
                    editable=editable, fields=fields, actions=[{'trigger':t['trigger'],'label':t.get('label') or 'Submit handover'} for t in transitions] if editable else [],
                    assigned_to_you=record.get('assignee_id')==actor.user_id)

    def rows(self, actor):
        try:
            own = self.own(actor)
        except AppError as exc:
            if exc.status in {403,404}:
                return []
            raise
        rows = self.platform.records(ENTITY, ['employee_id'])
        result = []
        for row in rows:
            if row['data'].get('employee_id') != own['entity_id']:
                continue
            try:
                result.append(self.detail(actor,row['entity_id']))
            except AppError as exc:
                if exc.status != 404:
                    raise
        return result

    def command(self, actor, entity_id, payload):
        with self.offboarding.journal.lock(actor.organization_id) as db:
            # Check scope even on replay, before returning a stored result.
            item = self.detail(actor,entity_id)
            op = self.offboarding.journal.operation(db,actor,payload['idempotency_key'],{'employee_offboarding':entity_id,'payload':payload})
            if op.result:
                return op.result
            if payload.get('trigger') and op.progress.get('target')==item['state']:
                op.finish({'entity_id':entity_id})
                return op.result
            if not item['editable']:
                raise AppError(403,'This form is not currently assigned to you')
            if item['values_hash'] not in {payload['expected_hash'],op.progress.get('saved_hash')}:
                raise AppError(409,'The form changed. Reload before continuing')
            trigger = payload.get('trigger')
            if trigger:
                if trigger not in {a['trigger'] for a in item['actions']}:
                    raise AppError(403,'Only your configured handover action is available')
                _,_,workflow,_ = self.context(actor,entity_id)
                target=next(t['to_state'] for t in workflow['definition']['transitions'] if t.get('from')==item['state'] and t['trigger']==trigger)
                op.checkpoint(target=target)
                self.platform.call('POST',f'/entities/{entity_id}/transitions',json={
                    'entity_id':entity_id,'workflow_id':workflow['id'],'trigger':trigger,'idempotency_key':payload['idempotency_key']})
            else:
                editable={f['field'] for f in item['fields'] if not f.get('read_only')}
                values=payload.get('values',{})
                if set(values)-editable:
                    raise AppError(403,'Only employee handover fields may be changed')
                merged={**item['values'],**values}
                op.checkpoint(saved_hash=digest(merged))
                self.platform.call('PUT',f'/entity-records/{entity_id}',json={'data':values})
            self.offboarding.journal.audit(db,actor,'offboarding.employee.'+(trigger or 'saved'),entity_id)
            op.finish({'entity_id':entity_id})
            return op.result
