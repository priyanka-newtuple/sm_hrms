"""WFH policy and allowance orchestration through native platform APIs only."""
from datetime import date, timedelta
import hashlib

from pydantic import BaseModel, ConfigDict, Field

from .catalog import pack_by_type
from .errors import AppError
from .policy import capabilities, require
from .service import name, LEAVE, LEAVE_FIELDS
from .wfh_catalog import POLICY, REQUEST
from .workflow_config import configured_workflow_rows


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    year: int = Field(ge=2000, le=2100)
    annual_days: int = Field(ge=0, le=366)
    notice_days: int = Field(ge=0, le=365)
    revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


class RequestInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dates: list[date] = Field(min_length=1, max_length=366)
    reason: str = Field(default='', max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trigger: str
    idempotency_key: str = Field(min_length=8, max_length=128)


def check(condition, message, status=422):
    if not condition:
        raise AppError(status, message)


def request_dates(row):
    return set(row['data']['dates'].splitlines())


class WfhService:
    def __init__(self, service):
        self.service = service
        self.platform, self.journal = service.platform, service.journal

    def rows(self, kind):
        fields = [f['field'] for f in pack_by_type(kind).fields]
        return self.platform.records(kind, [*fields, 'identifier', 'hrms_operation_key'])

    def validate_form(self, actor, kind, data, previous=None):
        from .form_config import form_configuration
        previous = previous or {}
        for field in form_configuration(self.platform, actor, kind)['fields']:
            key = field['field']
            if key not in data or key in {'employee_id', 'policy_id', 'revision', 'hrms_operation_key'}:
                continue
            check(not field.get('required') or data[key] not in (None, '', []), f'{key} is required by the configured form')
            check(not field.get('read_only') or data[key] == previous.get(key), f'{key} is read-only in the configured form')

    def states(self, kind):
        return self.platform.states(pack_by_type(kind).machine_name)

    def policy(self, year):
        rows = [r for r in self.rows(POLICY) if r['data']['year'] == year]
        check(len(rows) <= 1, 'Duplicate WFH policies require administrator reconciliation', 409)
        return rows[0] if rows else None

    def own(self, actor):
        employee = self.service.own_employee(actor, self.service.employees())
        check(employee['data'].get('employment_status') == 'active', 'An active employee profile is required', 403)
        return employee

    def guard_operations(self, db, org, key):
        # Durable intent reserves the tenant until an uncertain upstream write is replayed.
        row = db.execute("""SELECT operation_key FROM operations WHERE organization_id=%s
            AND operation_key<>%s AND result IS NULL AND progress ? 'wfh_plan' LIMIT 1""", (org, key)).fetchone()
        check(not row, 'A WFH operation is incomplete. Retry that operation before making another change.', 409)

    def transition(self, entity_id, trigger, key):
        return self.platform.call('POST', f'/entities/{entity_id}/transitions', json={
            'entity_id': entity_id, 'trigger': trigger, 'idempotency_key': key})

    def holiday_dates(self):
        # Reuse publication selection (including replacement versions and effective windows).
        from .cockpit import CockpitService
        feed = CockpitService(self.platform, self.journal).feed(employee=True)
        result = set()
        for item in feed:
            if item.get('entity_type') == 'HRMS.HolidayCalendar':
                for line in item.get('holidays', '').splitlines():
                    result.add(line.split('|', 1)[0].strip())
        return result

    def conflicts(self, employee_id, dates):
        states = self.platform.states('hrms_leaverequest')
        for row in self.platform.records(LEAVE, LEAVE_FIELDS):
            d = row['data']
            if d.get('employee_id') == employee_id and states.get(row['entity_id']) in {'pending', 'approved'}:
                check(not any(d['start_date'] <= day <= d['end_date'] for day in dates),
                      'These dates overlap a pending or approved leave request', 409)
        check(not dates.intersection(self.holiday_dates()), 'A selected date is a published holiday', 409)

    def reserved(self, employee_id, year, excluding=None):
        states = self.states(REQUEST)
        dates = set()
        for row in self.rows(REQUEST):
            if row['entity_id'] != excluding and row['data']['employee_id'] == employee_id and row['data']['year'] == year:
                # A record whose enrollment has not finished still reserves its dates.
                if states.get(row['entity_id'], 'pending') in {'pending', 'approved'}:
                    dates.update(request_dates(row))
        return dates

    def apply_plan(self, actor, op, key):
        plan = op.progress['wfh_plan']
        entity_id = plan.get('entity_id')
        if plan['mode'] == 'create':
            row = self.service._create_once(op, 'wfh', plan['kind'], plan['data'], actor.user_id,
                                            self.rows(plan['kind']), plan['data']['hrms_operation_key'])
            entity_id = row['entity_id']
            self.platform.enroll(entity_id, pack_by_type(plan['kind']).machine_name)
        elif plan['mode'] == 'update':
            self.platform.call('PUT', f'/entity-records/{entity_id}', json={'data': plan['data']})
        if plan.get('trigger'):
            self.transition(entity_id, plan['trigger'], key)
        result = {'entity_id': entity_id}
        self.journal.audit(op.db if hasattr(op, 'db') else None, actor, f'wfh.{plan["action"]}', entity_id, key)
        op.finish(result)
        return result

    def save_policy(self, actor, payload):
        check(actor.organization_id == self.platform.org, 'Organization mismatch', 403)
        require(actor, 'wfh:configure')
        check(payload.year >= date.today().year, 'Past-year policies cannot be changed')
        key = f'wfh-policy:{actor.user_id}:{payload.idempotency_key}'
        with self.journal.lock(actor.organization_id) as db:
            self.guard_operations(db, actor.organization_id, key)
            op = self.journal.operation(db, actor, key, payload.model_dump(mode='json'))
            if op.result:
                return op.result
            if 'wfh_plan' not in op.progress:
                row = self.policy(payload.year)
                check((row['data'].get('revision', 0) if row else 0) == payload.revision, 'Policy changed; reload before saving', 409)
                for employee in self.service.employees():
                    check(len(self.reserved(employee['entity_id'], payload.year)) <= payload.annual_days,
                          'Allowance cannot be lower than an employee’s pending and approved bookings', 409)
                data = payload.model_dump(exclude={'idempotency_key'})
                data['revision'] += 1
                data['hrms_operation_key'] = hashlib.sha256(key.encode()).hexdigest()
                self.validate_form(actor, POLICY, data, row['data'] if row else None)
                op.checkpoint(wfh_plan={'mode': 'update' if row else 'create', 'kind': POLICY,
                    'entity_id': row['entity_id'] if row else None, 'data': data,
                    'trigger': None if row else 'activate', 'action': 'policy_saved'})
            return self.apply_plan(actor, op, key)

    def create(self, actor, payload):
        check(actor.organization_id == self.platform.org, 'Organization mismatch', 403)
        require(actor, 'wfh:request')
        key = f'wfh-create:{actor.user_id}:{payload.idempotency_key}'
        with self.journal.lock(actor.organization_id) as db:
            self.guard_operations(db, actor.organization_id, key)
            op = self.journal.operation(db, actor, key, payload.model_dump(mode='json'))
            if op.result:
                return op.result
            if 'wfh_plan' not in op.progress:
                own = self.own(actor)
                dates = {d.isoformat() for d in payload.dates}
                year = payload.dates[0].year
                check(all(d.year == year for d in payload.dates), 'Submit each calendar year separately')
                check(all(d.weekday() < 5 for d in payload.dates), 'WFH is available on weekdays only')
                policy = self.policy(year)
                check(policy and self.states(POLICY).get(policy['entity_id']) == 'active', 'HR has not configured an active WFH policy for this year', 409)
                check(min(payload.dates) >= date.today() + timedelta(days=policy['data']['notice_days']), 'Dates do not meet the WFH notice period')
                reserved = self.reserved(own['entity_id'], year)
                check(not reserved.intersection(dates), 'A pending or approved WFH request already covers these dates', 409)
                check(len(reserved) + len(dates) <= policy['data']['annual_days'], 'Annual WFH allowance exceeded', 409)
                self.conflicts(own['entity_id'], dates)
                data = dict(employee_id=own['entity_id'], policy_id=policy['entity_id'], year=year,
                            dates='\n'.join(sorted(dates)), reason=payload.reason,
                            hrms_operation_key=hashlib.sha256(key.encode()).hexdigest())
                self.validate_form(actor, REQUEST, data)
                op.checkpoint(wfh_plan={'mode': 'create', 'kind': REQUEST, 'data': data, 'action': 'requested'})
            return self.apply_plan(actor, op, key)

    def decide(self, actor, entity_id, payload):
        check(actor.organization_id == self.platform.org, 'Organization mismatch', 403)
        require(actor, 'wfh:view')
        key = f'wfh-decision:{actor.user_id}:{payload.idempotency_key}'
        with self.journal.lock(actor.organization_id) as db:
            self.guard_operations(db, actor.organization_id, key)
            op = self.journal.operation(db, actor, key, {'entity_id': entity_id, **payload.model_dump()})
            if op.result:
                return op.result
            row = next((r for r in self.rows(REQUEST) if r['entity_id'] == entity_id), None)
            check(row, 'WFH request was not found', 404)
            employee = next((e for e in self.service.employees() if e['entity_id'] == row['data']['employee_id']), None)
            check(employee, 'Employee was not found', 404)
            own = employee['data'].get('platform_user_id') == actor.user_id
            if payload.trigger == 'cancel':
                check(own, 'Only the requester can cancel this request', 403)
            else:
                require(actor, 'wfh:approve')
                check(not own, 'Another HR approver must review your request', 403)
            if 'wfh_plan' not in op.progress:
                state = self.states(REQUEST).get(entity_id)
                check(payload.trigger in ({'approve', 'reject', 'cancel'} if state == 'pending' else {'cancel'} if state == 'approved' else set()), 'This action is no longer available', 409)
                if payload.trigger in {'cancel', 'approve'}:
                    check(min(request_dates(row)) >= date.today().isoformat(), 'Past dates cannot be approved or cancelled')
                if payload.trigger == 'approve':
                    check(employee['data'].get('employment_status') == 'active', 'Employee is no longer active', 409)
                    self.conflicts(row['data']['employee_id'], request_dates(row))
                op.checkpoint(wfh_plan={'mode': 'transition', 'entity_id': entity_id, 'trigger': payload.trigger, 'action': payload.trigger})
            return self.apply_plan(actor, op, key)

    def board(self, actor, year):
        check(actor.organization_id == self.platform.org, 'Organization mismatch', 403)
        require(actor, 'wfh:view')
        caps = capabilities(actor)
        employees = {e['entity_id']: e for e in self.service.employees()}
        own = [e for e in employees.values() if e['data'].get('platform_user_id') == actor.user_id]
        own_id = own[0]['entity_id'] if len(own) == 1 else None
        states = self.states(REQUEST)
        rows = [r for r in self.rows(REQUEST) if r['data']['year'] == year]
        visible, calendar = [], []
        for row in rows:
            d = row['data']; employee = employees.get(d['employee_id'])
            if not employee:
                continue
            state = states.get(row['entity_id'], 'pending')
            if state == 'approved':
                calendar.append(dict(employee_id=d['employee_id'], employee_name=name(employee),
                                     department=employee['data'].get('department', ''), dates=sorted(request_dates(row))))
            if d['employee_id'] == own_id or 'wfh:approve' in caps:
                actions = []
                if d['employee_id'] == own_id and state in {'pending', 'approved'} and min(request_dates(row)) >= date.today().isoformat():
                    actions = ['cancel']
                elif d['employee_id'] != own_id and 'wfh:approve' in caps and state == 'pending':
                    actions = ['approve', 'reject'] if min(request_dates(row)) >= date.today().isoformat() else ['reject']
                visible.append(dict(entity_id=row['entity_id'], employee_name=name(employee), dates=sorted(request_dates(row)),
                                    reason=d.get('reason', ''), state=state, actions=actions, is_mine=d['employee_id'] == own_id))
        visible = configured_workflow_rows(self.platform, visible)
        for row in visible:
            transitions = row['workflow_configuration']['transitions']
            row['actions'] = [a for a in row['actions'] if any(t['trigger'] == a and t['from_state'] == row['current_state'] for t in transitions)]
        policy = self.policy(year)
        policy_data = {k: policy['data'][k] for k in ('year', 'annual_days', 'notice_days', 'revision')} if policy else None
        mine = [r for r in rows if r['data']['employee_id'] == own_id]
        today = date.today().isoformat()
        approved = set().union(*(request_dates(r) for r in mine if states.get(r['entity_id']) == 'approved'))
        pending = set().union(*(request_dates(r) for r in mine if states.get(r['entity_id'], 'pending') == 'pending'))
        return dict(policy=policy_data, requests=visible, calendar=calendar, can_configure='wfh:configure' in caps,
                    can_approve='wfh:approve' in caps, can_request=bool(own_id and own[0]['data'].get('employment_status') == 'active' and 'wfh:request' in caps),
                    balance=dict(used=sum(d < today for d in approved), upcoming=sum(d >= today for d in approved), pending=len(pending),
                                 remaining=max(0, (policy_data['annual_days'] if policy else 0)-len(approved | pending))))

    def inbox(self, actor):
        check(actor.organization_id == self.platform.org, 'Organization mismatch', 403)
        require(actor, 'wfh:approve')
        years = {r['data']['year'] for r in self.rows(REQUEST)}
        return [r for year in sorted(years) for r in self.board(actor, year)['requests']
                if 'approve' in r['actions'] or 'reject' in r['actions']]

    def workflows(self, actor):
        if 'wfh:view' not in capabilities(actor):
            return []
        years = {r['data']['year'] for r in self.rows(REQUEST)}
        return [dict(entity_id=r['entity_id'], entity_type=REQUEST, title=r['employee_name'],
                     identifier='', current_state=r['state'], workflow_label='Work from home',
                     owner_name='HR' if r['state'] == 'pending' else r['employee_name'],
                     next_action=', '.join(r['actions']), progress=', '.join(r['dates']),
                     due_date=min(r['dates']), leave=None, leave_view=None, wfh=r)
                for year in sorted(years) for r in self.board(actor, year)['requests']]

    def check_leave_conflict(self, db, actor, employee_id, start_date, end_date):
        self.guard_operations(db, actor.organization_id, '')
        for year in range(start_date.year, end_date.year + 1):
            check(not any(start_date.isoformat() <= d <= end_date.isoformat() for d in self.reserved(employee_id, year)),
                  'Cancel overlapping WFH dates before requesting leave', 409)
