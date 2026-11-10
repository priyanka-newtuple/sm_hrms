"""Offboarding orchestration over public native APIs; native graph owns lifecycle."""
from datetime import datetime, UTC, date
from uuid import UUID
import json
import os
from html import escape
from urllib.parse import urlsplit

from .errors import AppError
from .offboarding_simple import enabled as simplified, departure_due, ROUTING, role_grants
from .policy import require, capabilities, field_access
from .offboarding_catalog import ENTITY, MACHINE, SYSTEM_FIELDS
from .offer_documents import digest
from .employee_work import transition_grants
from .offboarding_participation import EMPLOYEE_FIELDS, employee_step as is_employee_step
from .offboarding_checklist import SYSTEM_KEYS, EMPLOYEE_TRIGGERS, is_checklist, CONTACT_KEYS, staged_forms

SYSTEM = {f['field'] for f in SYSTEM_FIELDS} | SYSTEM_KEYS


def validate_clearances(values):
    for key, allowed in {
        'handover_status': {'Completed', 'Not applicable'},
        'asset_status': {'Completed', 'Exception approved', 'Not applicable'},
        'external_access_status': {'Completed', 'Not applicable'},
        'ownership_status': {'Completed', 'Not applicable'},
        'settlement_status': {'Confirmed', 'Not applicable'},
    }.items():
        if values.get(key) not in allowed:
            raise AppError(422, 'Complete ' + key.replace('_', ' '))
    for key in ('handover_notes', 'asset_notes', 'external_access_notes', 'ownership_notes', 'settlement_notes', 'final_notes'):
        if not str(values.get(key) or '').strip():
            raise AppError(422, 'Provide evidence or a not-applicable reason: ' + key.replace('_', ' '))


def validate_last_day(values):
    try:
        return date.fromisoformat(str(values['confirmed_last_day'])[:10])
    except (ValueError, KeyError):
        raise AppError(422, 'Enter a valid last working day')


class OffboardingService:
    def __init__(self, service):
        self.service = service
        self.platform, self.journal = service.platform, service.journal

    def call(self, actor, method, path, **kwargs):
        require(actor, 'employee:exit')
        return self.platform.request(method, path, token=actor.token, **kwargs)

    def assignees(self, actor):
        require(actor,'employee:exit')
        return [{'id':u['id'],'name':u.get('full_name') or u['email']} for u in self.platform.users()
                if u.get('status')=='active' and u.get('email')!=self.platform.email
                and 'employee:exit' in self.platform.user_capabilities(u['id'])]

    def routing_options(self, actor):
        require(actor, 'employee:exit')
        from .platform import Actor
        workflow = self.workflow(actor)
        result = {k: [] for k in ROUTING}
        for user in self.platform.users():
            if user.get('status') != 'active' or user.get('email') == self.platform.email:
                continue
            candidate = Actor(user['id'], actor.organization_id, '', frozenset(), frozenset())
            _, grants, workflows = role_grants(self.platform, candidate)
            if workflow['machine_name'] not in workflows:
                continue
            for key, trigger in [('offboarding_project_manager_id', 'approve_project_release'), ('offboarding_office_admin_id', 'confirm_asset_clearance'), ('offboarding_access_admin_id', 'disable_hrms_access')]:
                if any(t['trigger'] == trigger and (workflow['machine_name'], t['key']) in grants for t in workflow['definition']['transitions']):
                    result[key].append({'id': user['id'], 'name': user.get('full_name') or user['email']})
        return result

    def authorize_file(self, actor, method, path, query):
        if 'employee:exit' not in capabilities(actor):
            return False
        upload = method == 'POST' and path == 'filehandler/upload'
        if upload:
            entity_id = query.get('owner_entity_id')
            try:
                field_key = json.loads(query.get('metadata','{}')).get('field_key')
            except (ValueError, AttributeError):
                raise AppError(422, 'Document field metadata is required')
        elif method == 'GET' and len(path.split('/')) in {2,3}:
            parts=path.split('/')
            if len(parts)==3 and parts[2] not in {'download','download-url'}:
                return False
            metadata=self.call(actor,'GET',f'/filehandler/{parts[1]}')
            entity_id=metadata.get('owner_entity_id')
            field_key=(metadata.get('metadata') or {}).get('field_key')
        else:
            return False
        if not entity_id or not any(r['entity_id']==entity_id for r in self.rows(actor)):
            return False
        item=self.detail(actor,entity_id)
        fields=item['fields'] if upload else field_access(actor, ENTITY, item['workflow']['definition']['entity_schema']['fields'])
        field=next((f for f in fields if f['field']==field_key and f['type']=='document'),None)
        if not field or (upload and (not item['editable'] or field.get('read_only'))):
            raise AppError(403,'Document is not available in this offboarding state')
        return True

    def workflow(self, actor):
        listing = self.call(actor, 'GET', '/workflow-state-machines', params={'scope':'published'})
        matches = [w for w in listing['published_items'] if w['entity_type']==ENTITY and w['is_active']]
        if len(matches)!=1:
            raise AppError(409, 'Offboarding needs exactly one active native workflow')
        w = self.call(actor, 'GET', f"/workflow-state-machines/{matches[0]['id']}")
        if w['entity_type'] != ENTITY or w['organization_id'] != actor.organization_id:
            raise AppError(403, 'Offboarding workflow is not available')
        return w

    def employee(self, actor, employee_id):
        try:
            UUID(employee_id)
        except (ValueError, TypeError):
            raise AppError(422, 'Choose a valid employee')
        r = self.call(actor, 'GET', f'/entity-records/{employee_id}')
        kind = self.call(actor, 'GET', '/entity-types/HRMS.Employee')
        if r['organization_id'] != actor.organization_id or r['entity_type_id'] != kind['entity_type_id']:
            raise AppError(404, 'Employee not found')
        uid = r['data'].get('platform_user_id')
        identity = next((u for u in self.platform.users() if u['id'] == uid), None) if uid else None
        return r, identity

    def rows(self, actor):
        if 'employee:exit' not in capabilities(actor):
            return []
        result, offset, workflows = [], 0, {}
        while True:
            page = self.call(actor, 'GET', '/workflow-enrollments', params={
                'entity_type_name': ENTITY, 'fields': 'identifier,employee_id,confirmed_last_day', 'limit': 200, 'offset': offset})
            if page.get('scan_truncated'):
                raise AppError(502, 'Offboarding results are incomplete')
            for r in page['items']:
                if r['organization_id'] != actor.organization_id or r.get('entity_type')!=ENTITY:
                    raise AppError(502, 'Offboarding organization mismatch')
                wid=r['workflow_id']
                if wid not in workflows:
                    workflows[wid]=self.call(actor,'GET',f'/workflow-state-machines/{wid}')
                terminal=any(s['name']==r['current_state'] and 'terminal' in s.get('tags',[]) for s in workflows[wid]['definition']['states'])
                result.append({**r,'is_terminal':terminal})
            if not page.get('has_more'):
                return result
            if not page['items']:
                raise AppError(502, 'Offboarding results are incomplete')
            offset += len(page['items'])

    def fields(self, workflow, state):
        schemas = workflow['definition'].get('method_schemas', [])
        # A state may pin several forms that share a field; render each field once.
        fields, seen = [], set()
        for f in (f for s in schemas if s['state_name'] == state for f in s['fields']):
            if f['field'] not in seen:
                seen.add(f['field'])
                fields.append(f)
        return fields or workflow['definition']['entity_schema']['fields']

    def inbox(self, actor):
        result = []
        for r in self.rows(actor):
            if r['is_terminal']:
                continue
            if (r.get('assignee_id') or r.get('owner_id')) == actor.user_id and self.detail(actor, r['entity_id'])['actions']:
                result.append(r)
        return result

    def workflows(self, actor):
        result, definitions = [], {}
        for r in self.rows(actor):
            # One read per workflow version in this request, not one per case.
            if r['workflow_id'] not in definitions:
                definitions[r['workflow_id']] = self.call(actor, 'GET', f"/workflow-state-machines/{r['workflow_id']}")
            w = definitions[r['workflow_id']]
            states = [dict(name=s['name'],label=s['name'],terminal='terminal' in s.get('tags',[])) for s in w['definition']['states']]
            result.append(dict(entity_id=r['entity_id'],entity_type=ENTITY,title=r['summary_fields'].get('identifier') or r['entity_id'],
                identifier=r['summary_fields'].get('identifier'),current_state=r['current_state'],state_label=r['current_state'],
                is_terminal=any(s['name']==r['current_state'] and s['terminal'] for s in states),workflow_label=w['name'],owner_name=r.get('assignee_name') or r.get('owner_name') or '',assignee_id=r.get('assignee_id'),assignee_name=r.get('assignee_name'),next_action='',progress='',due_date=r.get('due_date'),leave=None,leave_view=None,
                workflow_configuration=dict(name=w['name'],version=w['version'],machine_name=w['machine_name'],states=states,transitions=[{**t,'from_state':t.get('from',t.get('from_state'))} for t in w['definition']['transitions']])))
        return result

    def config(self, actor):
        w = self.workflow(actor)
        fields=field_access(actor, ENTITY, self.fields(w, w['definition']['initial_state']))
        return dict(simplified=simplified(w), workflow=w, previous_fields=[], fields=[f for f in fields if f['field'] not in SYSTEM|EMPLOYEE_FIELDS])

    def detail(self, actor, entity_id):
        UUID(entity_id)
        response = self.call(actor, 'GET', f'/entity-records/{entity_id}/with-states')
        r = response['entity']
        kind = self.call(actor, 'GET', '/entity-types/' + ENTITY)
        if r['organization_id'] != actor.organization_id or r['entity_type_id'] != kind['entity_type_id']:
            raise AppError(404, 'Offboarding not found')
        states = response.get('states', [])
        if len(states) != 1:
            raise AppError(409, 'Offboarding needs one native workflow enrollment')
        state = states[0]
        w = self.call(actor, 'GET', f"/workflow-state-machines/{state['workflow_id']}")
        if w['entity_type'] != ENTITY or w['organization_id'] != actor.organization_id:
            raise AppError(403, 'Invalid offboarding workflow')
        employee, _ = self.employee(actor, r['data']['employee_id'])
        actions = self.call(actor, 'GET', f'/entities/{entity_id}/transitions/available', params={'workflow_id': w['id']})
        grants = transition_grants(self.platform, actor)
        permitted = {t['trigger'] for t in w['definition']['transitions'] if t.get('from')==state['current_state'] and
                     (grants is None or (w['machine_name'],t['key']) in grants)}
        terminal = any(s['name'] == state['current_state'] and 'terminal' in s.get('tags', []) for s in w['definition']['states'])
        assigned = r.get('assignee_id')
        employee_step=any(s['name']==state['current_state'] and is_employee_step(s) for s in w['definition']['states'])
        people={u['id']:u.get('full_name') or u['email'] for u in self.platform.users()}
        participation=any(is_employee_step(s) for s in w['definition']['states'])
        previous_fields = []
        if staged_forms(w):
            graph = w['definition']
            order = next(s['order'] for s in graph['states'] if s['name'] == state['current_state'])
            earlier = {s['name'] for s in graph['states'] if s['order'] < order}
            current_keys = {f['field'] for f in self.fields(w, state['current_state'])}
            prior = {f['field']: f for schema in graph.get('method_schemas', [])
                     if schema['state_name'] in earlier for f in schema['fields']
                     if f['field'] not in current_keys | SYSTEM and f['field'] in r['data']}
            previous_fields = [dict(f, read_only=True) for f in field_access(actor, ENTITY, list(prior.values()))]
        return dict(simplified=simplified(w), entity_id=entity_id, values=r['data'], values_hash=digest(r['data']), state=state['current_state'],assignee_id=assigned,assignee_name=people.get(assigned),employee_participation=participation,
            workflow=w, previous_fields=previous_fields, fields=[{**f,'read_only':True} if f['field'] in EMPLOYEE_FIELDS|SYSTEM|(CONTACT_KEYS if staged_forms(w) else set()) else f for f in field_access(actor, ENTITY, self.fields(w, state['current_state']))], editable=not terminal and (not employee_step or is_checklist(w)) and (not simplified(w) or assigned == actor.user_id),
            employee={k: employee['data'].get(k) for k in ('employee_code','first_name','last_name','department','designation','date_joined','employment_status')},
            actions=[a for a in actions.get('available_transitions', []) if a['trigger'] in permitted and a['trigger'] not in EMPLOYEE_TRIGGERS
                     and (not employee_step or (is_checklist(w) and a['trigger']=='confirm_departure'))
                     and (assigned in {None,actor.user_id} or 'superadmin' in actor.roles or (is_checklist(w) and a['trigger']=='confirm_departure' and r['data'].get('offboarding_coordinator_id')==actor.user_id))
                     and not (a['trigger']=='confirm_departure' and r['data'].get('departure_verified')=='yes')])

    def related(self, actor, entity_id):
        item = self.detail(actor, entity_id)
        employee_id = item['values']['employee_id']
        # HR-only summary uses public, tenant-scoped record APIs. Do not expose
        # commercial allocation fields or unrelated employees' private data.
        result = {}
        for label, kind, fields, predicate in [
            ('assets', 'HRMS.Asset', ['identifier','issued_employee_id','asset_name'], lambda d:d.get('issued_employee_id')==employee_id),
            ('allocations', 'HRMS.Allocation', ['identifier','employee_id','project_id','end_date'], lambda d:d.get('employee_id')==employee_id),
        ]:
            try:
                result[label] = {'items':[{'entity_id':r['entity_id'],**r['data']} for r in self.platform.records(kind,fields,token=actor.token) if predicate(r['data'])]}
            except AppError as e:
                result[label] = {'error':'Unable to verify linked records. Check this clearance manually.', 'status':e.status}
        employee, _ = self.employee(actor,employee_id)
        code = employee['data'].get('employee_code')
        result['direct_reports'] = {'items':[{'entity_id':r['entity_id'],'employee_code':r['data'].get('employee_code')}
            for r in self.platform.records('HRMS.Employee', ['employee_code','reports_to_employee_code','employment_status'], token=actor.token) if code and r['data'].get('reports_to_employee_code')==code and r['data'].get('employment_status')=='active']}
        return result

    def save(self, actor, payload, entity_id=None):
        require(actor, 'employee:exit')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, payload['idempotency_key'], {'save_offboarding': entity_id, 'payload': payload})
            if op.result:
                return op.result
            current = self.detail(actor, entity_id) if entity_id else None
            if current and (not current['editable'] or current['values_hash'] not in {payload['expected_hash'], op.progress.get('planned_hash')}):
                raise AppError(409, 'This record changed or is closed. Reload before saving')
            w = current['workflow'] if current else self.workflow(actor)
            fields = self.fields(w, current['state'] if current else w['definition']['initial_state'])
            allowed = {f['field'] for f in fields if not f.get('read_only')} - SYSTEM - EMPLOYEE_FIELDS - (CONTACT_KEYS if staged_forms(w) else set())
            if current:
                allowed.discard('employee_id')
                if current['values'].get('departure_verified') == 'yes':
                    allowed -= {'confirmed_last_day', 'exit_type'}
            submitted = payload.get('values', {})
            if set(submitted) - allowed:
                raise AppError(422, 'Only editable fields in this workflow state may be saved')
            values = {**(current['values'] if current else {}), **submitted}
            employee, identity = self.employee(actor, str(values.get('employee_id', '')))
            routing_keys=set() if simplified(w) else {'offboarding_coordinator_id'} if is_checklist(w) else {'offboarding_approver_id','offboarding_coordinator_id'}
            if any(k in values for k in routing_keys):
                eligible={u['id'] for u in self.assignees(actor)}
                if any(values.get(k) not in eligible for k in routing_keys):
                    raise AppError(422,'Choose active HR approver and coordinator accounts')
            if not current and employee['data'].get('employment_status') != 'active':
                raise AppError(409, 'Choose an active employee')
            if not current and is_checklist(w):
                if not staged_forms(w):
                    from pydantic import TypeAdapter, EmailStr, ValidationError
                    try:
                        TypeAdapter(EmailStr).validate_python(values.get('employee_notification_email'))
                    except ValidationError:
                        raise AppError(422,'Enter the employee-confirmed notification email')
                    if values.get('notification_email_confirmed')!='Yes':
                        raise AppError(422,'Confirm the employee-approved contact address')
                if not identity or identity.get('status')!='active':
                    raise AppError(409,'An active linked employee account is required')
                if simplified(w):
                    if not values.get('confirmed_last_day'):
                        raise AppError(422, 'Enter the last working day')
                    values['offboarding_coordinator_id'] = actor.user_id
                else:
                    validate_last_day(values)
                if not values.get('exit_type'): raise AppError(422,'Choose the exit type')
                coordinator=next((u for u in self.platform.users() if u['id']==values.get('offboarding_coordinator_id') and u['status']=='active'),None)
                if not coordinator: raise AppError(422,'Choose an active HR coordinator')
                address=urlsplit(os.environ.get('HRMS_PUBLIC_URL') or os.environ.get('GOOGLE_REDIRECT_URI',''))
                if address.scheme not in {'https','http'} or not address.hostname or address.username or address.password:
                    raise AppError(503,'Configure the MyHub public address before starting offboarding')
                values.update(offboarding_employee_user_id=identity['id'],offboarding_coordinator_email=coordinator['email'],
                    offboarding_workspace_url=escape(address.scheme+'://'+address.netloc+'/hrms/my-work',quote=True),
                    exit_employee_name=' '.join(str(employee['data'].get(k) or '') for k in ('first_name','last_name')).strip(),
                    exit_employee_code=employee['data'].get('employee_code'),exit_date_joined=employee['data'].get('date_joined'))
            if current and is_checklist(w) and 'offboarding_coordinator_id' in submitted:
                coordinator=next((u for u in self.platform.users() if u['id']==values.get('offboarding_coordinator_id') and u['status']=='active'),None)
                if not coordinator: raise AppError(422,'Choose an active HR coordinator')
                values['offboarding_coordinator_email']=coordinator['email']
            if simplified(w) and (not current or ROUTING & set(submitted)):
                options = self.routing_options(actor)
                for key in ROUTING & {f['field'] for f in fields}:
                    if values.get(key) not in {u['id'] for u in options[key]}:
                        raise AppError(422, 'Choose an active assignee with native clearance permissions')
                    if values[key] == (identity or {}).get('id'):
                        raise AppError(422, 'The departing employee cannot approve their own clearance')
            for f in fields:
                value = values.get(f['field'])
                if f.get('required') and not value:
                    raise AppError(422, 'Complete ' + f['field'])
                if value and f.get('enum_values') and value not in f['enum_values']:
                    raise AppError(422, 'Choose a configured value for ' + f['field'])
            if values.get('confirmed_last_day') and employee['data'].get('date_joined') and str(values['confirmed_last_day'])[:10] < str(employee['data']['date_joined'])[:10]:
                raise AppError(422, 'Last working day cannot precede the joining date')
            values['clearance_verified'] = ''
            if current and not simplified(w) and any(values.get(k) != current['values'].get(k) for k in ('confirmed_last_day',)):
                if not str(submitted.get('change_reason') or '').strip():
                    raise AppError(422, 'Give a reason for changing the last working day')
                values['notice_verified'] = ''
                if current['values'].get('notice_verified') == 'yes':
                    validate_last_day(values)
                    values['notice_verified'] = 'yes'
            if entity_id:
                # Persist the expected merged record before writes, so a lost
                # response can resume without accepting unrelated edits.
                op.checkpoint(planned_hash=digest(values))
                self.call(actor, 'PUT', f'/entity-records/{entity_id}', json={'data': submitted})
                # System flags are changed only through the explicitly authorized app service.
                self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': {k:v for k,v in values.items() if k in SYSTEM}})
                if values.get('notice_verified')=='yes' and values.get('departure_verified')!='yes':
                    self.platform.call('PUT', f"/entity-records/{employee['entity_id']}", json={'data':{'last_working_day':str(values['confirmed_last_day'])[:10]}})
            else:
                # Include un-enrolled records to detect interrupted creation too.
                existing = self.platform.records(ENTITY, ['employee_id','identifier'])
                states = self.platform.states(w['machine_name'])
                terminal={s['name'] for s in w['definition']['states'] if 'terminal' in s.get('tags',[])}
                identifier = 'Exit · ' + ' '.join(str(employee['data'].get(k) or '') for k in ('first_name','last_name')) + ' · ' + payload['idempotency_key'][:8]
                if op.progress.get('create_requested') and not op.progress.get('entity_id'):
                    recovered=next((r for r in existing if r['data'].get('identifier')==identifier and r['data'].get('employee_id')==values['employee_id']),None)
                    if not recovered:
                        raise AppError(409,'Creation outcome needs reconciliation before retrying; do not create another exit')
                    op.checkpoint(entity_id=recovered['entity_id'])
                if any(r['data'].get('employee_id') == values['employee_id'] and states.get(r['entity_id']) not in terminal
                       and r['entity_id'] != op.progress.get('entity_id') for r in existing):
                    raise AppError(409, 'This employee already has an open offboarding')
                if not op.progress.get('entity_id'):
                    kind = self.call(actor, 'GET', '/entity-types/' + ENTITY)
                    values['identifier'] = identifier
                    op.checkpoint(create_requested=True)
                    created = self.call(actor, 'POST', '/entity-records', json={'entity_type_id': kind['entity_type_id'], 'data': {k:v for k,v in values.items() if k not in SYSTEM}, 'owner_id': actor.user_id})
                    op.checkpoint(entity_id=created['entity_id'])
                entity_id = op.progress['entity_id']
                if is_checklist(w):
                    # Assignment/email state-entry actions must see routing first.
                    self.platform.call('PUT',f'/entity-records/{entity_id}',json={'data':{k:v for k,v in values.items() if k in SYSTEM}})
                enrollment = self.call(actor, 'GET', f'/entity-records/{entity_id}/with-states').get('states', [])
                if not enrollment:
                    self.call(actor, 'POST', f"/workflow-state-machines/{w['machine_name']}/enrollments", json={'entity_id': entity_id})
                elif len(enrollment) != 1 or enrollment[0]['workflow_id'] != w['id']:
                    raise AppError(409, 'The exit record has a different workflow enrollment; reconcile it before continuing')
            self.journal.audit(db, actor, 'offboarding.saved', entity_id)
            op.finish({'entity_id': entity_id})
            return op.result

    def act(self, actor, entity_id, payload):
        require(actor, 'employee:exit')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, payload['idempotency_key'], {'offboarding_action': entity_id, 'payload': payload})
            if op.result:
                return op.result
            item = self.detail(actor, entity_id)
            expected = op.progress.get('saved_hash', payload['expected_hash'])
            if item['values_hash'] not in {expected, op.progress.get('planned_hash')} and op.progress.get('target') != item['state']:
                raise AppError(409, 'This record changed. Reload before continuing')
            trigger = payload['trigger']
            transition = next((t for t in item['workflow']['definition']['transitions'] if t['trigger'] == trigger and t.get('from') == item['state']), None)
            if not transition:
                if op.progress.get('target') == item['state']:
                    op.finish({'entity_id': entity_id}); return op.result
                raise AppError(409, 'Action is not available in this state')
            if trigger not in {a['trigger'] for a in item['actions']}:
                raise AppError(403, 'Native transition permission is required')
            grants = transition_grants(self.platform, actor)
            if grants is not None and (item['workflow']['machine_name'],transition['key']) not in grants:
                raise AppError(403, 'Native transition permission is required')
            if 'workflow:write' not in actor.permissions:
                raise AppError(403, 'Native workflow write permission is required')
            values = item['values']
            verification = {'approve_exit':'notice_verified','confirm_departure':'departure_verified','disable_hrms_access':'departure_verified',
                            'approve_withdrawal':'withdrawal_verified','complete_offboarding':'clearance_verified'}.get(trigger)
            preview = self.call(actor, 'GET', f'/entities/{entity_id}/transitions/{trigger}/preflight', params={
                'machine_name':item['workflow']['machine_name'], 'workflow_id':item['workflow']['id'],
                'current_state':item['state'], 'inputs_json':json.dumps({verification:'yes'} if verification else {})})
            if not preview.get('allowed'):
                raise AppError(409, '; '.join(preview.get('blocked_reasons', [])) or 'Native workflow checks did not pass')
            for f in transition.get('required_fields', []):
                if f.get('required') and not values.get(f['field']):
                    raise AppError(422, 'Complete ' + f['field'])
            employee, identity = self.employee(actor, values['employee_id'])
            if trigger in EMPLOYEE_TRIGGERS:
                raise AppError(403,'Employee handover must be submitted by the assigned employee')
            if any(f['field']=='offboarding_approver_id' for f in item['workflow']['definition']['entity_schema']['fields']):
                # Prepare the dynamic native assignment and communication fields
                # before a state-entry action is queued.
                if trigger in {'submit_for_approval','resubmit','approve_exit'}:
                    from pydantic import TypeAdapter, EmailStr, ValidationError
                    try:
                        TypeAdapter(EmailStr).validate_python(values.get('employee_notification_email'))
                    except ValidationError:
                        raise AppError(422,'Enter the employee-confirmed notification email')
                    if values.get('notification_email_confirmed')!='Yes':
                        raise AppError(422,'Confirm the employee-approved contact address')
                    if not identity or identity.get('status')!='active':
                        raise AppError(409,'An active linked employee account is required for employee handover')
                    values['offboarding_employee_user_id']=identity['id']
            now = datetime.now(UTC)
            employee_data = dict(employee['data'])
            if trigger == 'approve_exit':
                validate_last_day(values)
                employee_data.update(last_working_day=str(values['confirmed_last_day'])[:10], exit_reason=values['exit_type'], exit_note=values.get('exit_reason'))
                values.update(notice_verified='yes', approved_at=now.isoformat())
            elif trigger in {'confirm_departure', 'disable_hrms_access'}:
                if simplified(item['workflow']):
                    departure_due(values, now)
                if trigger == 'disable_hrms_access' and not identity:
                    raise AppError(409, 'Linked HRMS account is required to verify access removal')
                if identity and identity['status'] in {'active','pending'}:
                    self.service._end_access(op, identity['id'], identity['status'], token=actor.token)
                    verified = next(u for u in self.platform.users() if u['id'] == identity['id'])
                    if verified['status'] in {'active','pending'}:
                        raise AppError(409, 'HRMS access removal could not be verified; retry')
                employee_data.update(employment_status='offboarded', last_working_day=str(values['confirmed_last_day'])[:10], exit_reason=values['exit_type'], exit_note=values.get('exit_reason'))
                values.update(departure_verified='yes', departed_at=now.isoformat())
            elif trigger == 'approve_withdrawal':
                if employee_data.get('employment_status') != 'active' or values.get('departure_verified') == 'yes':
                    raise AppError(409, 'A departed employee cannot be reactivated by withdrawing an exit')
                employee_data.update(last_working_day=None, exit_reason=None, exit_note=None)
                values['withdrawal_verified'] = 'yes'
            elif trigger == 'complete_offboarding':
                if not simplified(item['workflow']):
                    validate_clearances(values)
                if employee_data.get('employment_status') != 'offboarded' or (identity and identity['status'] in {'active','pending'}):
                    raise AppError(409, 'Employee departure and HRMS access removal must be verified')
                values.update(clearance_verified='yes', completed_at=now.isoformat())
            elif trigger in {'request_checklist_corrections','reopen_checklist'}:
                if not identity or identity.get('status')!='active':
                    raise AppError(409,'The employee no longer has access. Resolve remaining clearance with HR')
                values['checklist_verified']=''
                # A reopened form requires a new acknowledgment. Prior answers
                # and signature snapshots remain in the operation/audit history.
                self.platform.call('PUT',f'/entity-records/{entity_id}',json={'data':{'exit_acknowledgment':False}})
            if simplified(item['workflow']) and trigger in {'reopen_project_clearance', 'reopen_asset_clearance'}:
                reset = {'project_release_approved': '', 'clearance_assets_received': '', 'clearance_licenses_revoked': ''} if trigger == 'reopen_project_clearance' else {'clearance_assets_received': '', 'clearance_licenses_revoked': ''}
                self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': reset})
                values.update(reset)
            op.checkpoint(target=transition['to_state'], planned_hash=digest(values))
            if employee_data != employee['data']:
                self.platform.call('PUT', f"/entity-records/{employee['entity_id']}", json={'data': {k:v for k,v in employee_data.items() if employee['data'].get(k)!=v}})
            self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': {k:v for k,v in values.items() if k in SYSTEM}})
            op.checkpoint(saved_hash=digest(values))
            result = self.call(actor, 'POST', f'/entities/{entity_id}/transitions', json={
                'entity_id': entity_id, 'workflow_id': item['workflow']['id'], 'trigger': trigger, 'idempotency_key': payload['idempotency_key']})
            self.journal.audit(db, actor, 'offboarding.' + trigger, entity_id)
            op.finish({'entity_id': entity_id, 'result': result})
            return op.result
