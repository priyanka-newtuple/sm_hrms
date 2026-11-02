"""Relationship-scoped employee access, using public native APIs only.

Employees never receive broad native read access to confidential exit records.
This projection is a security ceiling; native methods further narrow the form.
"""
from .errors import AppError
from .offboarding_simple import enabled as simplified, role_grants
from .offboarding_catalog import ENTITY, SECTIONS
from .offer_documents import digest
from datetime import datetime, UTC
import json
from .offboarding_checklist import EMPLOYEE_KEYS, EMPLOYEE_TRIGGERS, is_checklist, validate_values, CONTACT_KEYS, staged_forms

def employee_step(state):
    return any(a['kind']=='entity.assign_user' and a.get('config',{}).get('user_id')=='$entity.offboarding_employee_user_id' for a in state.get('on_state_actions',[]))
EMPLOYEE_FIELDS = {f['field'] for f in SECTIONS['Employee handover']} | EMPLOYEE_KEYS
PUBLIC_FIELDS = EMPLOYEE_FIELDS | {'identifier', 'confirmed_last_day', 'requested_last_day', 'exit_employee_name', 'exit_employee_code', 'exit_date_joined', 'checklist_submitted_at', 'checklist_submitted_by', 'change_reason'}


class EmployeeOffboarding:
    def __init__(self, offboarding):
        self.offboarding = offboarding
        self.platform = offboarding.platform
        self.service = offboarding.service

    def own(self, actor):
        try:
            return self.service.own_employee(actor, self.service.employees())
        except AppError as exc:
            if exc.status in {403, 404}:
                return None
            raise

    def participant(self, actor, record, workflow):
        # Native assignments define participation, independently of whose turn it is.
        users = {record.get('assignee_id')}
        for state in workflow['definition']['states']:
            for action in state.get('on_state_actions', []):
                if action.get('kind') != 'entity.assign_user':
                    continue
                value = action.get('config', {}).get('user_id')
                if isinstance(value, str) and value.startswith('$entity.'):
                    value = record['data'].get(value[len('$entity.'):])
                if isinstance(value, str) and not value.startswith('$'):
                    users.add(value)
        if actor.user_id in users:
            return True
        # Retain progress visibility for people who have already handed work on.
        offset = 0
        while True:
            page = self.platform.call('GET', '/audit-events', params={
                'entity_id': record['entity_id'], 'event_type': 'ENTITY_ASSIGNEE_CHANGED',
                'limit': 200, 'offset': offset})
            for event in page['items']:
                if event.get('organization_id') != actor.organization_id or event.get('entity_id') != record['entity_id']:
                    raise AppError(502, 'Invalid assignment history scope')
                metadata = event.get('metadata') or {}
                if actor.user_id in {metadata.get('previous_assignee_id'), metadata.get('new_assignee_id')}:
                    return True
            offset += len(page['items'])
            if offset >= page['total']:
                return False
            if not page['items']:
                raise AppError(502, 'Incomplete assignment history')

    def context(self, actor, entity_id):
        own = self.own(actor)
        response = self.platform.call('GET', f'/entity-records/{entity_id}/with-states')
        record = response['entity']
        kind = self.platform.call('GET', '/entity-types/' + ENTITY)
        if (record['organization_id'] != actor.organization_id or record['entity_type_id'] != kind['entity_type_id']):
            raise AppError(404, 'Offboarding record is not available')
        if len(response['states']) != 1:
            raise AppError(409, 'Offboarding enrollment needs review')
        enrollment = response['states'][0]
        workflow = self.platform.call('GET', f"/workflow-state-machines/{enrollment['workflow_id']}")
        if workflow['organization_id'] != actor.organization_id or workflow['entity_type'] != ENTITY:
            raise AppError(403, 'Invalid workflow scope')
        if not (own and record['data'].get('employee_id') == own['entity_id']) and not self.participant(actor, record, workflow):
            raise AppError(404, 'Offboarding record is not available')
        state = next(s for s in workflow['definition']['states'] if s['name'] == enrollment['current_state'])
        if ('initial' in state.get('tags', []) and not is_checklist(workflow)) or state['name']=='Discarded':
            raise AppError(404, 'Offboarding has not been initiated')
        return record, enrollment, workflow, state

    def detail(self, actor, entity_id):
        record, enrollment, workflow, state = self.context(actor, entity_id)
        own = self.own(actor)
        is_employee = bool(own and record['data'].get('employee_id') == own['entity_id'])
        if simplified(workflow):
            return self.simple_detail(actor, record, workflow, state, is_employee)
        if not is_employee:
            # Participants get stage visibility, never employee feedback or HR evidence.
            values = {k: v for k, v in record['data'].items() if k in {'identifier', 'exit_employee_name', 'exit_employee_code', 'confirmed_last_day'}}
            return dict(entity_id=entity_id, state=state['name'], values=values, values_hash=digest(values),
                        editable=False, fields=[], sections=[], assets=[], actions=[],
                        assigned_to_you=record.get('assignee_id') == actor.user_id, viewer='participant')
        employee_fields = EMPLOYEE_FIELDS | (CONTACT_KEYS if staged_forms(workflow) else set())
        visible = employee_fields | ({'exit_employee_name','exit_employee_code','exit_date_joined','confirmed_last_day'} if is_checklist(workflow) else set())
        fields = [{**f, 'read_only':f.get('read_only',False) or f['field'] not in employee_fields} for f in self.offboarding.fields(workflow, state['name']) if f['field'] in visible]
        editable = employee_step(state) and record.get('assignee_id') == actor.user_id
        values = {k:v for k,v in record['data'].items() if k in PUBLIC_FIELDS | (CONTACT_KEYS if staged_forms(workflow) else set())}
        transitions = [t for t in workflow['definition']['transitions'] if t.get('from') == state['name'] and t['trigger'] in EMPLOYEE_TRIGGERS]
        required = {f['field'] for t in workflow['definition']['transitions'] if t['trigger']=='submit_checklist' for f in t.get('required_fields',[]) if f.get('required')}
        fields = [{**f,'required':True} if f['field'] in required else f for f in fields]
        sections = []
        for schema in workflow['definition'].get('method_schemas',[]):
            if schema['state_name'] != state['name']: continue
            keys = {f['field'] for f in schema['fields']}
            selected = [f for f in fields if f['field'] in keys]
            if selected and schema['method_name'].startswith(('Exit checklist v2 · ', 'Exit checklist v3 · ')) and schema['method_name'] not in {'Exit checklist v2 · Exit administration','Exit checklist v2 · Clearance verification'}:
                sections.append({'title':schema['method_name'].split(' · ',1)[-1],'fields':selected})
        assets, asset_error = [], None
        if is_checklist(workflow):
            try:
                assets=[{'identifier':r['data'].get('identifier'),'asset_name':r['data'].get('asset_name')} for r in self.platform.records('HRMS.Asset',['identifier','asset_name','issued_employee_id']) if r['data'].get('issued_employee_id')==record['data']['employee_id']]
            except AppError:
                asset_error='We could not check your assigned assets. Ask Office Admin to confirm your return list.'
        return dict(entity_id=entity_id, state=state['name'], values=values, values_hash=digest(values),
                    viewer='employee', editable=editable, fields=fields, sections=sections, assets=assets, asset_error=asset_error, actions=[{'trigger':t['trigger'],'label':t.get('label') or 'Submit handover'} for t in transitions] if editable else [],
                    assigned_to_you=record.get('assignee_id')==actor.user_id)

    def simple_detail(self, actor, record, workflow, state, is_employee):
        grants, transitions, workflows = role_grants(self.platform, actor)
        machine = workflow['machine_name']
        participant_fields = {'offboarding_employee_user_id', 'offboarding_project_manager_id', 'offboarding_office_admin_id'}
        assigned_step = any(a.get('kind') == 'entity.assign_user' and a.get('config', {}).get('user_id') in {'$entity.' + k for k in participant_fields} for a in state.get('on_state_actions', []))
        assigned = record.get('assignee_id') == actor.user_id
        active = assigned_step and assigned and machine in workflows
        actions = [t for t in workflow['definition']['transitions'] if t.get('from') == state['name'] and (machine, t['key']) in transitions and t['trigger'] not in {'confirm_departure', 'complete_offboarding'}] if active else []
        fields = [{**f, 'read_only': bool(f.get('read_only')) or not grants.get(f['field'], (False, False))[1]} for f in self.offboarding.fields(workflow, state['name']) if active and grants.get(f['field'], (False, False))[0]]
        # Only this assigned stage's form is exposed. HR interview feedback stays private.
        keys = {f['field'] for f in fields} | {'identifier', 'exit_employee_name', 'exit_employee_code', 'confirmed_last_day'}
        if is_employee:
            keys |= {'employee_notification_email', 'exit_projects_handed_over', 'exit_tasks_updated', 'project_clearance_comments', 'checklist_submitted_at'}
        values = {k: v for k, v in record['data'].items() if k in keys}
        assets, asset_error = [], None
        if active and record['data'].get('offboarding_office_admin_id') == actor.user_id:
            try:
                assets = [{'entity_id': r['entity_id'], 'identifier': r['data'].get('identifier'), 'asset_name': r['data'].get('asset_name')} for r in self.platform.records('HRMS.Asset', ['identifier', 'asset_name', 'issued_employee_id']) if r['data'].get('issued_employee_id') == record['data']['employee_id']]
            except AppError:
                asset_error = 'Unable to load assigned assets. Retry before confirming clearance.'
        return dict(entity_id=record['entity_id'], state=state['name'], viewer='employee' if is_employee else 'participant', values=values, values_hash=digest(values), fields=fields, sections=[], assets=assets, asset_error=asset_error, editable=active and bool(actions), assigned_to_you=assigned, actions=[{'trigger': t['trigger'], 'label': t.get('label') or t['trigger'], 'required_fields': t.get('required_fields', [])} for t in actions])

    def rows(self, actor):
        rows = self.platform.records(ENTITY, ['employee_id'])
        result = []
        for row in rows:
            if row['organization_id'] != actor.organization_id:
                raise AppError(502, 'Invalid offboarding scope')
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
            _,_,workflow,_ = self.context(actor,entity_id)
            if trigger:
                if trigger not in {a['trigger'] for a in item['actions']}:
                    raise AppError(403,'Only your configured handover action is available')
                target=next(t['to_state'] for t in workflow['definition']['transitions'] if t.get('from')==item['state'] and t['trigger']==trigger)
                if simplified(workflow):
                    record, _, _, _ = self.context(actor, entity_id)
                    if trigger == 'return_employee_checklist':
                        employee_user = next((u for u in self.platform.users() if u['id'] == record['data'].get('offboarding_employee_user_id')), None)
                        if not employee_user or employee_user.get('status') != 'active':
                            raise AppError(409, 'The employee no longer has login access. HR must resolve the remaining clearance.')
                    transition = next(t for t in workflow['definition']['transitions'] if t.get('from') == item['state'] and t['trigger'] == trigger)
                    required = {f['field'] for f in transition.get('required_fields', []) if f.get('required')}
                    validate_values([{**f, 'required': f['field'] in required} for f in item['fields']], item['values'], submitting=True)
                    preview = self.platform.call('GET', f'/entities/{entity_id}/transitions/{trigger}/preflight', params={'machine_name': workflow['machine_name'], 'workflow_id': workflow['id'], 'current_state': item['state'], 'inputs_json': json.dumps({'checklist_verified': 'yes'} if trigger == 'submit_checklist' else {})})
                    if not preview.get('allowed'):
                        raise AppError(409, '; '.join(preview.get('blocked_reasons', [])) or 'Complete the required clearance')
                    if trigger == 'confirm_asset_clearance':
                        if item.get('asset_error') or item.get('assets'):
                            raise AppError(409, 'Record the return of all assigned assets before confirming clearance')
                    if trigger in {'return_employee_checklist', 'return_project_clearance'}:
                        reset = {'project_release_approved': '', 'clearance_assets_received': '', 'clearance_licenses_revoked': ''}
                        self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': reset})
                if trigger=='submit_checklist':
                    validate_values(item['fields'], item['values'], submitting=True)
                    # Freeze an authenticated submission snapshot before transition;
                    # retries reuse the timestamp/revision and never forge identity.
                    if 'submission' not in op.progress:
                        record,_,_,_ = self.context(actor,entity_id)
                        op.checkpoint(submission={'checklist_submitted_at':datetime.now(UTC).isoformat(),'checklist_submitted_by':actor.user_id,
                            'checklist_revision':str(int(record['data'].get('checklist_revision') or 0)+1),'checklist_verified':'yes'}, answers=item['values'])
                        history=json.loads(record['data'].get('checklist_submission_history') or '[]')
                        history.append({'submission':dict(op.progress['submission']),'answers':item['values']})
                        op.checkpoint(submission={**op.progress['submission'],'checklist_submission_history':json.dumps(history)})
                    self.platform.call('PUT',f'/entity-records/{entity_id}',json={'data':op.progress['submission']})
                    op.checkpoint(saved_hash=digest({**item['values'],**{k:v for k,v in op.progress['submission'].items() if k in PUBLIC_FIELDS | (CONTACT_KEYS if staged_forms(workflow) else set())}}))
                op.checkpoint(target=target)
                self.platform.call('POST',f'/entities/{entity_id}/transitions',json={
                    'entity_id':entity_id,'workflow_id':workflow['id'],'trigger':trigger,'idempotency_key':payload['idempotency_key']})
            else:
                editable={f['field'] for f in item['fields'] if not f.get('read_only')}
                values=payload.get('values',{})
                if set(values)-editable:
                    raise AppError(403,'Only employee handover fields may be changed')
                if ('employee_notification_email' in values and values['employee_notification_email'] != item['values'].get('employee_notification_email')
                        and 'notification_email_confirmed' not in values and not simplified(workflow)):
                    values = {**values, 'notification_email_confirmed': ''}
                merged={**item['values'],**values}
                if is_checklist(workflow): validate_values(item['fields'], merged)
                op.checkpoint(saved_hash=digest(merged))
                self.platform.call('PUT',f'/entity-records/{entity_id}',json={'data':values})
                if is_checklist(workflow) and item['state']==workflow['definition']['initial_state']:
                    self.platform.call('POST',f'/entities/{entity_id}/transitions',json={'entity_id':entity_id,'workflow_id':workflow['id'],'trigger':'start_checklist','idempotency_key':payload['idempotency_key']+'-start'})
            self.offboarding.journal.audit(db,actor,'offboarding.employee.'+(trigger or 'saved'),entity_id,payload['idempotency_key'])
            op.finish({'entity_id':entity_id})
            return op.result
