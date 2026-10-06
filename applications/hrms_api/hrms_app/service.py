"""HRMS composition and business rules over the native platform HTTP API."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import json
from pathlib import Path

from .errors import AppError
from .onboarding_template import DEFAULT_ONBOARDING_STEPS
from .policy import capabilities, require

EMPLOYEE = 'HRMS.Employee'
CASE = 'HRMS.OnboardingCase'
LEAVE = 'HRMS.LeaveRequest'
EMPLOYEE_FIELDS = ['identifier', 'employee_code', 'first_name', 'last_name', 'work_email',
                   'department', 'designation', 'employment_status', 'reports_to_employee_code',
                   'platform_user_id', 'hrms_role', 'employment_type', 'date_joined', 'work_location',
                   'notice_period_days', 'phone', 'hrms_operation_key']
CASE_FIELDS = ['identifier', 'employee_id', 'template_key', 'template_version', 'hrms_operation_key']
LEAVE_FIELDS = ['identifier', 'employee_id', 'manager_id', 'start_date', 'end_date',
                'leave_type', 'reason', 'hrms_operation_key']
ROLE_NAMES = {'hrms_office_admin': 'Office Admin', 'hrms_finance': 'Finance',
              'hrms_hr_full': 'HR Full', 'hrms_hr_basic': 'HR Basic',
              'hrms_delivery_manager': 'Delivery Manager'}
REFERENCE_OPTIONS = json.loads(Path(__file__).with_name('reference_options.json').read_text())


def name(row):
    return f"{row['data'].get('first_name', '')} {row['data'].get('last_name', '')}".strip()


def task_for_step(tasks, step):
    matches = [task for task in tasks if task.get('stage') == f'onboarding-step-{step.sequence}'
               or (task.get('description') or '').startswith(f'HRMS onboarding step {step.sequence};')]
    if len(matches) > 1:
        raise AppError(409, 'Duplicate onboarding tasks require reconciliation')
    return matches[0] if matches else None


class HrmsService:
    def __init__(self, platform, journal, domain):
        self.platform, self.journal, self.domain = platform, journal, domain

    def employees(self):
        return self.platform.records(EMPLOYEE, EMPLOYEE_FIELDS)

    @staticmethod
    def employee_item(row, rows):
        data = row['data']
        manager = next((m for m in rows if m['data'].get('employee_code') ==
                        data.get('reports_to_employee_code') and data.get('reports_to_employee_code')), None)
        return dict(entity_id=row['entity_id'], employee_code=data.get('employee_code') or '',
                    full_name=name(row), work_email=data.get('work_email') or '',
                    department=data.get('department') or '', designation=data.get('designation') or '',
                    reports_to_name=name(manager) if manager else None,
                    employment_status=data.get('employment_status') or '', role=data.get('hrms_role') or 'hrms_employee')

    def directory(self, actor):
        require(actor, 'employee:read')
        rows = self.employees()
        return sorted([self.employee_item(row, rows) for row in rows], key=lambda r: r['full_name'].casefold())

    def form_options(self, actor):
        require(actor, 'employee:create')
        rows = self.employees()
        roles = ['hrms_employee']
        if 'employee:assign_hr_role' in capabilities(actor):
            roles += ['hrms_manager', 'hrms_hr_basic']
        if 'employee:assign_hr_full' in capabilities(actor):
            roles += ['hrms_hr_full']
        return dict(departments=sorted(set(REFERENCE_OPTIONS['departments']) | {r['data']['department'] for r in rows if r['data'].get('department')}),
                    designations=sorted(set(REFERENCE_OPTIONS['designations']) | {r['data']['designation'] for r in rows if r['data'].get('designation')}), roles=roles)

    def onboarding(self, actor, case_id=None):
        employees = {r['entity_id']: r for r in self.employees()}
        cases = self.platform.records(CASE, CASE_FIELDS)
        if case_id:
            cases = [c for c in cases if c['entity_id'] == case_id]
        states = self.platform.states('hrms_onboardingcase')
        users = {u['id']: u['full_name'] for u in self.platform.users()}
        steps_by_case = self.platform.steps_by_case()
        caps, result = capabilities(actor), []
        for case in cases:
            tasks = steps_by_case.get(case['entity_id'], [])
            if 'employee:read' not in caps and not any(t.get('assigned_to') == actor.user_id for t in tasks):
                continue
            if case['data'].get('template_version') != 1 or case['data'].get('template_key') != 'default_onboarding':
                raise AppError(409, 'This onboarding template version is not supported')
            employee = employees.get(case['data'].get('employee_id'))
            if employee is None:
                raise AppError(409, 'Onboarding employee was not found')
            completed = {s.sequence for s in DEFAULT_ONBOARDING_STEPS
                         if (t := task_for_step(tasks, s)) and t['status'] == 'COMPLETED'}
            state = states.get(case['entity_id'], 'not_started')
            steps = []
            for step in DEFAULT_ONBOARDING_STEPS:
                task = task_for_step(tasks, step)
                readiness = ('completed' if step.sequence in completed else 'waiting'
                             if any(d not in completed for d in step.depends_on) else 'ready')
                steps.append(dict(sequence=step.sequence, task_id=task['id'] if task else None,
                    title=step.title, status=task['status'].lower() if task else 'not_started',
                    readiness=readiness, owner_name=users.get(task.get('assigned_to'), 'Unassigned') if task else 'Unassigned',
                    owner_role=ROLE_NAMES.get(step.assignee_role, 'New employee'),
                    due_date=task.get('due_date') if task else None, depends_on=list(step.depends_on),
                    can_complete=bool(task and state == 'in_progress' and readiness == 'ready'
                        and task['status'] not in {'COMPLETED', 'CANCELLED'}
                        and ('onboarding:manage' in caps or task.get('assigned_to') == actor.user_id))))
            result.append(dict(entity_id=case['entity_id'], identifier=case['data'].get('identifier') or '',
                employee_entity_id=employee['entity_id'], employee_name=name(employee),
                employee_code=employee['data'].get('employee_code') or '', designation=employee['data'].get('designation') or '',
                department=employee['data'].get('department') or '', state=state, completed_steps=len(completed),
                total_steps=len(DEFAULT_ONBOARDING_STEPS), steps=steps,
                can_complete_case='onboarding:manage' in caps and state == 'in_progress'
                    and len(completed) == len(DEFAULT_ONBOARDING_STEPS)))
        if case_id and not result:
            raise AppError(404, 'Onboarding case was not found or is not assigned to you')
        return sorted(result, key=lambda r: r['employee_name'].casefold())

    def complete_step(self, actor, case_id, sequence):
        with self.journal.lock(actor.organization_id) as db:
            case = self.onboarding(actor, case_id)[0]
            step = next((s for s in case['steps'] if s['sequence'] == sequence), None)
            if step is None:
                raise AppError(404, 'Onboarding step was not found')
            task = next(t for t in self.platform.tasks(case_id) if t['id'] == step['task_id']) if step['task_id'] else None
            if not task or ('onboarding:manage' not in capabilities(actor) and task.get('assigned_to') != actor.user_id):
                raise AppError(403, 'Only the assigned owner or HR manager can complete this step')
            if step['status'] != 'completed':
                if not step['can_complete']:
                    raise AppError(409, 'Complete prerequisite steps first; the case must be in progress')
                # Record intent before the remote mutation; operation outcome remains in platform task state.
                self.journal.audit(db, actor, 'onboarding.step.complete.requested', step['task_id'])
                self.platform.call('POST', f"/entities/{step['task_id']}/transitions", json={
                    'entity_id': step['task_id'], 'trigger': 'complete',
                    'idempotency_key': f"hrms:step:{actor.user_id}:{step['task_id']}"})
                self.journal.audit(db, actor, 'onboarding.step.completed', step['task_id'])
            return self.onboarding(actor, case_id)[0]

    def complete_case(self, actor, case_id):
        require(actor, 'onboarding:manage')
        with self.journal.lock(actor.organization_id) as db:
            case = self.onboarding(actor, case_id)[0]
            if case['state'] != 'completed':
                if not case['can_complete_case']:
                    raise AppError(409, 'Complete all onboarding steps before closing the case')
                self.journal.audit(db, actor, 'onboarding.complete.requested', case_id)
                self.platform.call('POST', f'/entities/{case_id}/transitions', json={
                    'entity_id': case_id, 'trigger': 'complete',
                    'idempotency_key': f'hrms:{actor.user_id}:complete:{case_id}'})
                self.journal.audit(db, actor, 'onboarding.completed', case_id)
            return self.onboarding(actor, case_id)[0]

    def create_employee(self, actor, request):
        require(actor, 'employee:create')
        payload = request.model_dump(mode='json')
        if request.role not in self.form_options(actor)['roles']:
            raise AppError(403, 'You cannot assign the requested employee role')
        email = str(request.work_email).lower().strip()
        if email.rsplit('@', 1)[-1] != self.domain:
            raise AppError(400, f'Work email must be on @{self.domain}')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee:{request.idempotency_key}', payload)
            if op.result:
                return {**op.result, 'idempotent': True}
            rows = self.employees()
            options = self.form_options(actor)
            if request.department not in options['departments'] or request.designation not in options['designations']:
                raise AppError(400, 'Select an active department and designation')
            manager = next((r for r in rows if r['entity_id'] == request.reports_to_entity_id), None)
            if request.reports_to_entity_id and (not manager or manager['data'].get('employment_status') != 'active'):
                raise AppError(400, 'Reporting manager must be active in this organization')
            marker = hashlib.sha256(f'{actor.organization_id}:employee:{request.idempotency_key}'.encode()).hexdigest()
            existing = next((r for r in rows if str(r['data'].get('work_email', '')).lower() == email), None)
            if existing and existing['data'].get('hrms_operation_key') != marker:
                raise AppError(409, 'An employee with this work email already exists')
            data = {k: v for k, v in payload.items() if k not in {'idempotency_key', 'reports_to_entity_id', 'role'}}
            data.update(work_email=email, employment_status='active', hrms_role=request.role,
                        reports_to_employee_code=manager['data'].get('employee_code') if manager else None,
                        hrms_operation_key=marker)
            if not existing:
                existing = self._create_once(op, 'employee', EMPLOYEE, data, actor.user_id, rows, marker)
            employee_id = existing['entity_id']
            op.checkpoint(employee_id=employee_id)
            # The public registration API creates a pending account without activating login.
            users = self.platform.users()
            identity = next((u for u in users if u['email'].lower() == email), None)
            if identity and not op.progress.get('identity_requested'):
                raise AppError(409, 'A platform account with this work email already exists')
            if not identity:
                org = self.platform.call('GET', '/organizations/current')
                if (org.get('domain') or '').lower() != self.domain:
                    raise AppError(409, 'Configure the HRMS organization email domain before provisioning employees')
                if op.progress.get('identity_requested'):
                    raise AppError(409, 'Identity creation needs reconciliation before retrying')
                op.checkpoint(identity_requested=True)
                response = self.platform.request('POST', '/auth/register', json={
                    'email': email, 'full_name': f'{request.first_name} {request.last_name}',
                    'password': secrets.token_urlsafe(48), 'role': 'hrms_employee'})
                if response.get('organization_id') != actor.organization_id or response.get('approval_type') != 'pending_org_admin':
                    raise AppError(409, 'Identity provisioning did not return a pending account in this organization')
                identity = next(u for u in self.platform.users() if u['id'] == response['user_id'])
            if identity['status'] not in {'pending', 'suspended'}:
                raise AppError(409, 'The new employee identity must remain pending or suspended')
            roles = self.platform.call('GET', '/roles')
            role = next((r for r in roles if r['name'] == request.role), None)
            if not role:
                raise AppError(409, 'The requested HRMS role has not been installed')
            self.platform.call('PUT', f"/roles/users/{identity['id']}/role", json={'role_id': role['id']})
            current = self.platform.record(employee_id)
            data = {**current['data'], 'employee_code': current['data']['identifier'], 'platform_user_id': identity['id']}
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': data})
            cases = self.platform.records(CASE, CASE_FIELDS)
            case = next((c for c in cases if c['data'].get('employee_id') == employee_id), None)
            if not case:
                case = self._create_once(op, 'case', CASE, dict(employee_id=employee_id,
                    template_key='default_onboarding', template_version=1, hrms_operation_key=marker), actor.user_id, cases, marker)
            case_id = case['entity_id']
            state = self.platform.enroll(case_id, 'hrms_onboardingcase')
            tasks = self.platform.tasks(case_id)
            active_ids = {u['id'] for u in users if u['status'] == 'active'}
            for step in DEFAULT_ONBOARDING_STEPS:
                if (existing_step := task_for_step(tasks, step)):
                    if existing_step['status'] == 'NOT_STARTED':
                        self.platform.enroll(existing_step['id'], 'hrms_onboardingstep')
                    continue
                key = f'task_{step.sequence}_requested'
                if op.progress.get(key):
                    raise AppError(409, 'Task creation needs reconciliation before retrying')
                owner = identity['id']
                if step.assignee_role:
                    candidates = [r for r in rows if r['data'].get('hrms_role') == step.assignee_role
                                  and r['data'].get('platform_user_id') in active_ids]
                    if not candidates:
                        candidates = [r for r in rows if r['data'].get('hrms_role') == 'hrms_hr_full'
                                      and r['data'].get('platform_user_id') in active_ids]
                    owner = candidates[0]['data']['platform_user_id'] if candidates else actor.user_id
                op.checkpoint(**{key: True})
                step_row = self.platform.create_record('HRMS.OnboardingStep', {
                    'case_id': case_id, 'sequence': step.sequence,
                    'title': step.title, 'description': f'HRMS onboarding step {step.sequence}; template v1; created by {actor.user_id}.',
                    'assigned_to': owner, 'due_date': (datetime.now(UTC) + timedelta(days=step.due_days)).isoformat(),
                    'hrms_operation_key': f'{marker}:{step.sequence}'}, actor.user_id)
                self.platform.enroll(step_row['entity_id'], 'hrms_onboardingstep')
                tasks = self.platform.tasks(case_id)
            final = self.platform.record(employee_id)
            result = dict(employee=self.employee_item(final, rows), onboarding_entity_id=case_id,
                          onboarding_state=state, onboarding_task_count=len(DEFAULT_ONBOARDING_STEPS),
                          account_status='pending', idempotent=False)
            self.journal.audit(db, actor, 'employee.created', employee_id)
            op.finish(result)
            return result

    def _create_once(self, op, key, entity_type, data, owner, rows, marker):
        existing = next((r for r in rows if r['data'].get('hrms_operation_key') == marker), None)
        if existing:
            return existing
        if op.progress.get(f'{key}_requested'):
            # A network timeout may follow a committed create. Do not blindly duplicate it.
            raise AppError(409, 'Creation outcome is uncertain; reconciliation is required')
        op.checkpoint(**{f'{key}_requested': True})
        try:
            return self.platform.create_record(entity_type, data, owner)
        except AppError as exc:
            if exc.status < 500:
                op.checkpoint(**{f'{key}_requested': False})
            raise

    def own_employee(self, actor, rows):
        own = [r for r in rows if r['data'].get('platform_user_id') == actor.user_id]
        if len(own) != 1:
            raise AppError(403, 'Your account has no unique employee profile')
        return own[0]

    def leave(self, actor, view, limit, offset):
        employees = self.employees()
        own = self.own_employee(actor, employees)
        if view == 'mine':
            visible = [own]
        elif view == 'approvals':
            visible = [r for r in employees if r['data'].get('reports_to_employee_code') == own['data'].get('employee_code')
                       and r['entity_id'] != own['entity_id']]
        else:
            raise AppError(400, 'view must be mine or approvals')
        names = {r['entity_id']: name(r) for r in visible}
        states = self.platform.states('hrms_leaverequest')
        rows = [r for r in self.platform.records(LEAVE, LEAVE_FIELDS) if r['data'].get('employee_id') in names]
        return [dict(entity_id=r['entity_id'], identifier=r['data'].get('identifier') or '',
                     employee_name=names[r['data']['employee_id']], start_date=r['data']['start_date'],
                     end_date=r['data']['end_date'], leave_type=r['data']['leave_type'], reason=r['data'].get('reason'),
                     state=states.get(r['entity_id'], 'not_enrolled')) for r in rows[offset:offset + limit]]

    def create_leave(self, actor, request):
        require(actor, 'leave:create')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'leave:{request.idempotency_key}', request.model_dump(mode='json'))
            if op.result:
                return {**op.result, 'idempotent': True}
            employees = self.employees()
            own = self.own_employee(actor, employees)
            managers = [r for r in employees if r['data'].get('employee_code') == own['data'].get('reports_to_employee_code')]
            if len(managers) != 1 or not managers[0]['data'].get('platform_user_id'):
                raise AppError(400, 'Your employee profile has no linked reporting manager')
            marker = hashlib.sha256(f'{actor.organization_id}:{actor.user_id}:leave:{request.idempotency_key}'.encode()).hexdigest()
            rows = self.platform.records(LEAVE, LEAVE_FIELDS)
            from .wfh import WfhService
            WfhService(self).check_leave_conflict(db, actor, own['entity_id'], request.start_date, request.end_date)
            states = self.platform.states('hrms_leaverequest')
            for row in rows:
                d = row['data']
                if d.get('hrms_operation_key') == marker:
                    continue
                if (d.get('employee_id') == own['entity_id'] and states.get(row['entity_id'], 'pending') in {'pending', 'approved'}
                    and d['start_date'] <= request.end_date.isoformat() and d['end_date'] >= request.start_date.isoformat()):
                    raise AppError(409, 'A pending or approved leave request overlaps these dates')
            data = request.model_dump(mode='json', exclude={'idempotency_key'})
            data.update(employee_id=own['entity_id'], manager_id=managers[0]['entity_id'], hrms_operation_key=marker)
            row = self._create_once(op, 'leave', LEAVE, data, actor.user_id, rows, marker)
            state = self.platform.enroll(row['entity_id'], 'hrms_leaverequest')
            result = dict(entity_id=row['entity_id'], identifier=row['data'].get('identifier') or '', state=state, idempotent=False)
            self.journal.audit(db, actor, 'leave.created', row['entity_id'])
            op.finish(result)
            return result

    def leave_actions(self, actor, entity_id):
        row = self.platform.record(entity_id)
        leave_type = self.platform.call('GET', f'/entity-types/{LEAVE}')
        if row['entity_type_id'] != leave_type['entity_type_id']:
            raise AppError(404, 'Leave request was not found')
        employees = self.employees()
        owner = next((e for e in employees if e['entity_id'] == row['data'].get('employee_id')), None)
        if not owner:
            raise AppError(404, 'Employee was not found')
        own = owner['data'].get('platform_user_id') == actor.user_id
        managers = [e for e in employees if e['data'].get('employee_code') == owner['data'].get('reports_to_employee_code')]
        manager = len(managers) == 1 and managers[0]['data'].get('platform_user_id') == actor.user_id and not own
        if not own and not manager:
            raise AppError(404, 'Leave request was not found')
        state = self.platform.states('hrms_leaverequest').get(entity_id)
        allowed = (['cancel'] if own else ['approve', 'reject'] if 'leave:decide' in capabilities(actor) else []) if state == 'pending' else []
        return dict(entity_id=entity_id, current_state=state, available_transitions=[
            dict(trigger=t, label=t.title(), allowed=True) for t in allowed])

    def decide_leave(self, actor, entity_id, trigger, key):
        with self.journal.lock(actor.organization_id) as db:
            # Actor-scoped journal prevents the core's broader replay key from authorizing another actor.
            op = self.journal.operation(db, actor, f'decision:{key}', {'entity_id': entity_id, 'trigger': trigger})
            available = self.leave_actions(actor, entity_id)
            if op.result:
                return op.result
            if trigger not in [t['trigger'] for t in available['available_transitions']]:
                raise AppError(403, 'This leave action is not available to you')
            self.journal.audit(db, actor, f'leave.{trigger}.requested', entity_id)
            result = self.platform.call('POST', f'/entities/{entity_id}/transitions', json={
                'entity_id': entity_id, 'trigger': trigger,
                'idempotency_key': f'hrms:{actor.user_id}:{key}'})
            self.journal.audit(db, actor, f'leave.{trigger}.completed', entity_id)
            op.finish(result)
            return result
