"""HRMS composition and business rules over the native platform HTTP API."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import secrets
import json
from pathlib import Path

from .custom_fields import check_custom, custom_keys, custom_values
from .errors import AppError
from .employee_access import identity_roles, may_manage
from .onboarding_template import CURRENT_TEMPLATE_VERSION, DEFAULT_ONBOARDING_STEPS, REPORTING_MANAGER, TEMPLATES
from .policy import capabilities, require

EMPLOYEE = 'HRMS.Employee'
CASE = 'HRMS.OnboardingCase'
LEAVE = 'HRMS.LeaveRequest'
ALLOCATION_FIELDS = ['project_id', 'employee_id', 'start_date', 'end_date']
LIVE_ALLOCATION = {'planned', 'active'}
EMPLOYEE_FIELDS = ['identifier', 'employee_code', 'first_name', 'last_name', 'work_email',
                   'department', 'designation', 'employment_status', 'reports_to_employee_code',
                   'platform_user_id', 'hrms_role', 'employment_type', 'date_joined', 'work_location',
                   'notice_period_days', 'phone', 'last_working_day', 'exit_reason', 'exit_note',
                   'hrms_operation_key']
OFFBOARDED = 'offboarded'
CASE_FIELDS = ['identifier', 'employee_id', 'template_key', 'template_version', 'cancelled_at', 'cancelled_by',
               'cancel_reason', 'hrms_operation_key']
LEAVE_FIELDS = ['identifier', 'employee_id', 'manager_id', 'start_date', 'end_date',
                'leave_type', 'reason', 'hrms_operation_key']
ROLE_NAMES = {'hrms_office_admin': 'Office Admin', 'hrms_finance': 'Finance',
              'hrms_hr_full': 'HR Full', 'hrms_hr_basic': 'HR Basic',
              'hrms_delivery_manager': 'Delivery Manager', REPORTING_MANAGER: 'Reporting manager'}
DONE = {'COMPLETED', 'CANCELLED'}  # a skipped step no longer holds anything up
SICK_LEAVE_BACKDATE_DAYS = 7
INVITE_STEP = next(s for s in DEFAULT_ONBOARDING_STEPS if s.key == 'hrms_invitation')
REFERENCE_OPTIONS = json.loads(Path(__file__).with_name('reference_options.json').read_text())


def fingerprint(request):
    """A request as its idempotency record sees it. No custom fields means the same request as before
    custom fields existed, so a retry sent across that deploy still matches."""
    payload = request.model_dump(mode='json')
    if not payload.get('custom'):
        payload.pop('custom', None)
    return payload


def name(row):
    return f"{row['data'].get('first_name', '')} {row['data'].get('last_name', '')}".strip()


def task_for_step(tasks, step):
    matches = [task for task in tasks if task.get('stage') == f'onboarding-step-{step.sequence}'
               or (task.get('description') or '').startswith(f'HRMS onboarding step {step.sequence};')]
    if len(matches) > 1:
        raise AppError(409, 'Duplicate onboarding tasks require reconciliation')
    return matches[0] if matches else None


def leave_days(start, end, holidays):
    """Working days in an inclusive ISO date range: weekdays that are not published holidays."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    days = (first + timedelta(offset) for offset in range((last - first).days + 1))
    return sum(1 for day in days if day.weekday() < 5 and day.isoformat() not in holidays)


def reporting_manager(employee, employees):
    """The one other employee, with a login, whose code is this employee's reports_to."""
    code = employee['data'].get('reports_to_employee_code')
    found = [e for e in employees if code and e['data'].get('employee_code') == code
             and e['entity_id'] != employee['entity_id'] and e['data'].get('platform_user_id')
             and e['data'].get('employment_status') != OFFBOARDED]
    return found[0] if len(found) == 1 else None


class LeaveApprovers:
    """Who may decide a leave request: the project manager of every project the employee is
    allocated to over the leave dates (any one of them decides), else the reporting manager,
    else (someone nobody manages, such as the CEO) HR Full. Nobody approves their own leave."""

    def __init__(self, platform, employees):
        self.platform, self.employees, self._hr = platform, employees, None
        states = platform.states('hrms_allocation')
        self.allocations = [r for r in platform.records('HRMS.Allocation', ALLOCATION_FIELDS)
                            if states.get(r['entity_id']) in LIVE_ALLOCATION]
        self.pm_of = {r['entity_id']: r['data'].get('pm_id') for r in platform.records('HRMS.Project', ['pm_id'])}

    def __call__(self, employee, start, end):
        pms = {self.pm_of.get(a['data'].get('project_id')) for a in self.allocations
               if a['data'].get('employee_id') == employee['entity_id']
               and a['data'].get('start_date', '') <= end and a['data'].get('end_date', '') >= start}
        pms -= {None, '', employee['data'].get('platform_user_id')}
        pms -= {e['data'].get('platform_user_id') for e in self.employees if e['data'].get('employment_status') == OFFBOARDED}
        if pms:
            return pms
        manager = reporting_manager(employee, self.employees)
        if manager:
            return {manager['data']['platform_user_id']}
        return self.hr_full() - {employee['data'].get('platform_user_id')}

    def hr_full(self):
        if self._hr is None:
            self._hr = {u['id'] for u in self.platform.users() if u.get('role') == 'hrms_hr_full' and u.get('status') == 'active'}
        return self._hr


class HrmsService:
    def __init__(self, platform, journal, domain):
        self.platform, self.journal, self.domain = platform, journal, domain

    def employees(self):
        return self.platform.records(EMPLOYEE, EMPLOYEE_FIELDS)

    @staticmethod
    def employee_item(row, rows, keys=()):
        """`keys`: custom fields (added in Settings) to include."""
        data = row['data']
        manager = next((m for m in rows if m['data'].get('employee_code') ==
                        data.get('reports_to_employee_code') and data.get('reports_to_employee_code')), None)
        return dict(entity_id=row['entity_id'], employee_code=data.get('employee_code') or '',
                    full_name=name(row), work_email=data.get('work_email') or '',
                    department=data.get('department') or '', designation=data.get('designation') or '',
                    reports_to_name=name(manager) if manager else None,
                    employment_status=data.get('employment_status') or '', role=data.get('hrms_role') or 'hrms_employee',
                    reports_to_entity_id=manager['entity_id'] if manager else None,
                    date_joined=data.get('date_joined'), employment_type=data.get('employment_type'),
                    work_location=data.get('work_location'), notice_period_days=data.get('notice_period_days'),
                    phone=data.get('phone'), last_working_day=data.get('last_working_day'),
                    exit_reason=data.get('exit_reason'), custom=custom_values(data, keys),
                    on_notice=bool(data.get('employment_status') == 'active' and data.get('last_working_day')
                                   and data['last_working_day'] > datetime.now(UTC).date().isoformat()))

    def directory(self, actor):
        require(actor, 'employee:read')
        keys = custom_keys(self.platform, EMPLOYEE)
        rows = self.platform.records(EMPLOYEE, EMPLOYEE_FIELDS + keys)
        users = {u['id']: u for u in self.platform.users()}
        states = self.platform.states('hrms_onboardingcase')
        cases = {c['data'].get('employee_id'): c for c in self.platform.records(CASE, CASE_FIELDS)}
        result = []
        for row in rows:
            item = self.employee_item(row, rows, keys)
            user = users.get(row['data'].get('platform_user_id'))
            if user and user.get('role'):
                item['role'] = user['role']  # Current role; the employee record keeps the role it was created with.
            item['account_status'] = user['status'] if user else 'not_linked'
            item['uses_google_sign_in'] = bool(user and user.get('auth_type') == 'google')
            item['can_setup_access'] = bool(user and user.get('organization_id') == actor.organization_id
                and user['status'] in {'pending', 'active'} and item['employment_status'] == 'active'
                and 'employee:activate' in capabilities(actor)
                and may_manage(actor, identity_roles(self.platform, actor, user)))
            case = cases.get(row['entity_id'])
            item['onboarding_state'] = ('not_started' if not case else 'cancelled' if case['data'].get('cancelled_at')
                                        else states.get(case['entity_id'], 'not_started'))
            result.append(item)
        return sorted(result, key=lambda r: r['full_name'].casefold())

    def form_options(self, actor):
        require(actor, 'employee:create')
        rows = self.employees()
        roles = ['hrms_employee']
        if 'employee:assign_hr_role' in capabilities(actor):
            # Office Admin and Finance own onboarding steps (ID, payroll, laptop), so HR must be able to add them.
            roles += ['hrms_manager', 'hrms_hr_basic', 'hrms_office_admin', 'hrms_finance']
        if 'employee:assign_hr_full' in capabilities(actor):
            roles += ['hrms_hr_full', 'hrms_project_manager', 'hrms_delivery_manager']
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
            if 'onboarding:view' not in caps and not any(t.get('assigned_to') == actor.user_id for t in tasks):
                continue
            try:
                template = TEMPLATES.get(case['data'].get('template_version'))
                if template is None or case['data'].get('template_key') != 'default_onboarding':
                    raise AppError(409, 'This onboarding template version is not supported')
                employee = employees.get(case['data'].get('employee_id'))
                if employee is None:
                    raise AppError(409, 'Onboarding employee was not found')
                done = {s.sequence for s in template if (t := task_for_step(tasks, s)) and t['status'] in DONE}
                skipped = {s.sequence for s in template if (t := task_for_step(tasks, s)) and t['status'] == 'CANCELLED'}
                # A cancelled onboarding (no-show, withdrawn offer) keeps its workflow state but is shown as cancelled.
                state = 'cancelled' if case['data'].get('cancelled_at') else states.get(case['entity_id'], 'not_started')
                manage = 'onboarding:manage' in caps and state == 'in_progress'
                steps = []
                for step in template:
                    task = task_for_step(tasks, step)
                    readiness = ('skipped' if step.sequence in skipped else 'completed' if step.sequence in done else 'waiting'
                                 if any(d not in done for d in step.depends_on) else 'ready')
                    open_task = bool(task and task['status'] not in DONE)
                    steps.append(dict(sequence=step.sequence, task_id=task['id'] if task else None,
                        title=step.title, status=task['status'].lower() if task else 'not_started',
                        readiness=readiness, owner_name=users.get(task.get('assigned_to'), 'Unassigned') if task else 'Unassigned',
                        owner_role=ROLE_NAMES.get(step.assignee_role, 'New employee'),
                        due_date=task.get('due_date') if task else None, depends_on=list(step.depends_on),
                        assigned_to_me=bool(task and task.get('assigned_to') == actor.user_id),
                        can_complete=bool(open_task and state == 'in_progress' and readiness == 'ready'
                            and ('onboarding:manage' in caps or task.get('assigned_to') == actor.user_id)),
                        can_manage=bool(open_task and manage)))
                result.append(dict(entity_id=case['entity_id'], identifier=case['data'].get('identifier') or '',
                    employee_entity_id=employee['entity_id'], employee_name=name(employee),
                    employee_code=employee['data'].get('employee_code') or '', designation=employee['data'].get('designation') or '',
                    department=employee['data'].get('department') or '', state=state, completed_steps=len(done),
                    total_steps=len(template), steps=steps, cancel_reason=case['data'].get('cancel_reason'),
                    can_complete_case=manage and len(done) == len(template), can_cancel=manage))
            except AppError:
                if case_id:
                    raise  # Acting on this case needs it readable.
                continue  # One unreadable case must not hide everyone else's onboarding.
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

    def _editable_employee(self, rows, employee_id):
        employee = next((r for r in rows if r['entity_id'] == employee_id), None)
        if not employee:
            raise AppError(404, 'Employee was not found')
        if employee['data'].get('employment_status') == OFFBOARDED:
            raise AppError(409, 'This employee has left; their record can no longer be changed')
        return employee

    def _check_reporting_manager(self, rows, employee, manager_id):
        """An active employee other than this one, and not someone who reports up to them."""
        if not manager_id:
            return None
        manager = next((r for r in rows if r['entity_id'] == manager_id), None)
        if not manager or manager['data'].get('employment_status') != 'active':
            raise AppError(400, 'Reporting manager must be active in this organization')
        by_code = {r['data'].get('employee_code'): r for r in rows if r['data'].get('employee_code')}
        seen, current = set(), manager
        while current is not None and current['entity_id'] not in seen:
            if current['entity_id'] == employee['entity_id']:
                raise AppError(400, 'An employee cannot report to themselves or to someone who reports to them')
            seen.add(current['entity_id'])
            current = by_code.get(current['data'].get('reports_to_employee_code'))
        return manager

    def update_employee(self, actor, employee_id, request):
        require(actor, 'employee:create')
        payload = request.model_dump(mode='json')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee-update:{request.idempotency_key}', {**payload, 'employee_id': employee_id})
            if op.result:
                return op.result
            rows = self.employees()
            employee = self._editable_employee(rows, employee_id)
            options = self.form_options(actor)
            current = employee['data']
            # Keep a value that is no longer offered (an older department, say) rather than refuse the edit.
            for key, choices in (('department', options['departments']), ('designation', options['designations'])):
                if getattr(request, key) not in choices and getattr(request, key) != current.get(key):
                    raise AppError(400, 'Select an active department and designation')
            manager = self._check_reporting_manager(rows, employee, request.reports_to_entity_id)
            record = self.platform.record(employee_id)
            custom = check_custom(self.platform, EMPLOYEE, request.custom, record['data'])
            data = {**record['data'], **{k: v for k, v in payload.items() if k not in {'idempotency_key', 'reports_to_entity_id', 'custom'}},
                    **custom, 'reports_to_employee_code': manager['data'].get('employee_code') if manager else None}
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': data})
            self.journal.audit(db, actor, 'employee.updated', employee_id)
            result = self.employee_item({**employee, 'data': data}, rows, list(custom))
            op.finish(result)
            return result

    def exit_employee(self, actor, employee_id, request):
        """Record an employee leaving. A future last working day leaves them active and on notice;
        on or after it they are offboarded and their sign-in is suspended. Calling again on or
        after the last day completes a notice period. Exits, terminations included, are for HR Full."""
        require(actor, 'employee:exit')
        payload = request.model_dump(mode='json')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee-exit:{request.idempotency_key}', {**payload, 'employee_id': employee_id})
            if op.result:
                return op.result
            rows = self.employees()
            employee = self._editable_employee(rows, employee_id)
            joined = employee['data'].get('date_joined')
            never_joined = request.reason == 'did_not_join'
            if joined and not never_joined and request.last_working_day.isoformat() < str(joined)[:10]:
                raise AppError(400, 'The last working day cannot be before the joining date')
            user_id = employee['data'].get('platform_user_id')
            identity = next((u for u in self.platform.users() if u['id'] == user_id), None) if user_id else None
            if identity and not may_manage(actor, identity_roles(self.platform, actor, identity)):
                raise AppError(403, 'Only Super Admin can record the exit of a privileged account')
            leaving = never_joined or request.last_working_day <= datetime.now(UTC).date()
            record = self.platform.record(employee_id)['data']
            # Completing a notice period without a new note keeps the note recorded with the resignation.
            data = {**record, 'last_working_day': payload['last_working_day'],
                    'exit_reason': request.reason, 'exit_note': request.note or record.get('exit_note'),
                    'employment_status': OFFBOARDED if leaving else 'active'}
            if leaving and identity and identity['status'] in {'active', 'pending'}:
                self._end_access(op, user_id, identity['status'])
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': data})
            self.journal.audit(db, actor, 'employee.offboarded' if leaving else 'employee.notice_recorded', employee_id)
            result = self.employee_item({**employee, 'data': data}, rows)
            op.finish(result)
            return result

    def _end_access(self, op, user_id, status):
        """Suspend the leaver's membership here; an invite never activated is also rejected so it
        cannot be approved later. A retry tolerates steps the interrupted attempt already did."""
        retry = op.progress.get('suspend_requested')
        op.checkpoint(suspend_requested=True)
        steps = ['suspend'] + (['reject'] if status == 'pending' else [])
        for step in steps:
            try:
                self.platform.call('POST', f'/users/{user_id}/{step}')
            except AppError:
                if not retry:
                    raise

    def withdraw_exit(self, actor, employee_id, idempotency_key):
        """A resignation withdrawn while the employee is still on notice."""
        require(actor, 'employee:exit')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee-exit-withdraw:{idempotency_key}', {'employee_id': employee_id})
            if op.result:
                return op.result
            rows = self.employees()
            employee = self._editable_employee(rows, employee_id)
            if not employee['data'].get('last_working_day'):
                raise AppError(409, 'This employee has no exit to withdraw')
            data = {**self.platform.record(employee_id)['data'], 'last_working_day': None, 'exit_reason': None, 'exit_note': None}
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': data})
            self.journal.audit(db, actor, 'employee.exit_withdrawn', employee_id)
            result = self.employee_item({**employee, 'data': data}, rows)
            op.finish(result)
            return result

    def complete_invite_step(self, employee_id):
        """After HR activates a hire's account, mark "Invite employee to HRMS" done, once the work
        account it depends on exists. Best effort: activation has already succeeded, and the step
        can still be completed by hand now that the account is active."""
        cases = [c for c in self.platform.records(CASE, CASE_FIELDS) if c['data'].get('employee_id') == employee_id]
        if not cases:
            return
        states = self.platform.states('hrms_onboardingcase')
        for case in cases:
            if states.get(case['entity_id']) != 'in_progress':
                continue
            try:
                tasks = self.platform.tasks(case['entity_id'])
                invite = task_for_step(tasks, INVITE_STEP)
                if not invite or invite['status'] in {'COMPLETED', 'CANCELLED'}:
                    continue
                if any((t := task_for_step(tasks, s)) is None or t['status'] != 'COMPLETED'
                       for s in DEFAULT_ONBOARDING_STEPS if s.sequence in INVITE_STEP.depends_on):
                    continue
                self.platform.call('POST', f"/entities/{invite['id']}/transitions", json={
                    'entity_id': invite['id'], 'trigger': 'complete', 'idempotency_key': f"hrms:invite:{invite['id']}"})
            except AppError:
                continue

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

    def _open_case_step(self, actor, case_id, sequence):
        require(actor, 'onboarding:manage')
        case = self.onboarding(actor, case_id)[0]
        step = next((s for s in case['steps'] if s['sequence'] == sequence), None)
        if step is None:
            raise AppError(404, 'Onboarding step was not found')
        if not step['can_manage']:
            raise AppError(409, 'Only open steps of an onboarding in progress can be changed')
        return step

    def onboarding_assignees(self, actor):
        """Active accounts HR can hand an onboarding step to."""
        require(actor, 'onboarding:manage')
        return sorted(({'id': u['id'], 'name': u.get('full_name') or u.get('email', '')} for u in self.platform.users()
                       if u.get('status') == 'active' and u.get('email') != getattr(self.platform, 'email', None)),
                      key=lambda u: u['name'].casefold())

    def update_step(self, actor, case_id, sequence, assigned_to, due_date):
        """HR hands a step to someone else or moves its due date."""
        with self.journal.lock(actor.organization_id) as db:
            step = self._open_case_step(actor, case_id, sequence)
            active = {u['id'] for u in self.platform.users() if u.get('status') == 'active'}
            if assigned_to and assigned_to not in active:
                raise AppError(400, 'Assign the step to an active user')
            record = self.platform.record(step['task_id'])
            data = {**record['data'], **({'assigned_to': assigned_to} if assigned_to else {}),
                    **({'due_date': datetime.combine(due_date, time(12), tzinfo=UTC).isoformat()} if due_date else {})}
            self.platform.call('PUT', f"/entity-records/{step['task_id']}", json={'data': data})
            self.journal.audit(db, actor, 'onboarding.step.updated', step['task_id'])
            return self.onboarding(actor, case_id)[0]

    def skip_step(self, actor, case_id, sequence, reason):
        """A step that does not apply to this hire (no laptop needed, say). Later steps stop waiting on it."""
        with self.journal.lock(actor.organization_id) as db:
            step = self._open_case_step(actor, case_id, sequence)
            self._cancel_step(db, actor, step['task_id'], reason)
            return self.onboarding(actor, case_id)[0]

    def _cancel_step(self, db, actor, task_id, reason):
        record = self.platform.record(task_id)
        self.platform.call('PUT', f'/entity-records/{task_id}', json={'data': {**record['data'], 'skip_reason': reason}})
        self.platform.call('POST', f'/entities/{task_id}/transitions', json={
            'entity_id': task_id, 'trigger': 'cancel', 'idempotency_key': f'hrms:skip:{task_id}'})
        self.journal.audit(db, actor, 'onboarding.step.skipped', task_id)

    def cancel_onboarding(self, actor, case_id, reason):
        """The hire will not join (no-show, withdrawn offer): open steps are cancelled and the case is
        shown as cancelled. Their exit is recorded separately in Org Directory."""
        require(actor, 'onboarding:manage')
        with self.journal.lock(actor.organization_id) as db:
            case = self.onboarding(actor, case_id)[0]
            if case['state'] == 'cancelled':
                return case
            if not case['can_cancel']:
                raise AppError(409, 'Only an onboarding in progress can be cancelled')
            self._cancel_case(db, actor, case_id, reason)
            return self.onboarding(actor, case_id)[0]

    def _cancel_case(self, db, actor, case_id, reason):
        record = self.platform.record(case_id)
        self.platform.call('PUT', f'/entity-records/{case_id}', json={'data': {
            **record['data'], 'cancelled_at': datetime.now(UTC).isoformat(), 'cancelled_by': actor.user_id, 'cancel_reason': reason}})
        for task in self.platform.tasks(case_id):
            if task['status'] not in DONE:
                self._cancel_step(db, actor, task['id'], reason)
        self.journal.audit(db, actor, 'onboarding.cancelled', case_id)

    def end_onboarding_of_leaver(self, actor, employee_id):
        """Someone offboarded before finishing onboarding: their open onboarding is cancelled."""
        states = self.platform.states('hrms_onboardingcase')
        with self.journal.lock(actor.organization_id) as db:
            for case in self.platform.records(CASE, CASE_FIELDS):
                if (case['data'].get('employee_id') == employee_id and not case['data'].get('cancelled_at')
                        and states.get(case['entity_id']) == 'in_progress'):
                    self._cancel_case(db, actor, case['entity_id'], 'Employee left before onboarding finished')

    def create_employee(self, actor, request):
        require(actor, 'employee:create')
        payload = fingerprint(request)
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
            users = self.platform.users()
            identity = next((u for u in users if u['email'].lower() == email), None)
            if identity:
                if identity.get('organization_id') != actor.organization_id or identity['status'] not in {'pending', 'active'}:
                    raise AppError(409, 'Existing account requires administrator review')
                if any(r['data'].get('platform_user_id') == identity['id'] and r is not existing for r in rows):
                    raise AppError(409, 'This account is already linked to an employee')
                assigned = identity_roles(self.platform, actor, identity)
                if op.progress.get('identity_requested') and assigned - {'hrms_employee', request.role}:
                    raise AppError(409, 'Account roles changed during provisioning; administrator reconciliation is required')
                if not op.progress.get('identity_requested') and (request.role not in assigned or
                        (assigned - {'hrms_employee'} and 'platform:configure' not in capabilities(actor))):
                    raise AppError(403, 'Existing account access must be reviewed by Super Admin; select its current role')
            data = {k: v for k, v in payload.items() if k not in {'idempotency_key', 'reports_to_entity_id', 'role', 'custom'}}
            data.update(check_custom(self.platform, EMPLOYEE, request.custom))
            data.update(work_email=email, employment_status='active', hrms_role=request.role,
                        reports_to_employee_code=manager['data'].get('employee_code') if manager else None,
                        hrms_operation_key=marker)
            if not existing:
                existing = self._create_once(op, 'employee', EMPLOYEE, data, actor.user_id, rows, marker)
            employee_id = existing['entity_id']
            op.checkpoint(employee_id=employee_id)
            # The public registration API creates a pending account without activating login.
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
            if identity['status'] not in {'pending', 'active'}:
                raise AppError(409, 'The employee identity must be pending or active')
            roles = self.platform.call('GET', '/roles')
            role = next((r for r in roles if r['name'] == request.role), None)
            if not role:
                raise AppError(409, 'The requested HRMS role has not been installed')
            if op.progress.get('identity_requested') and identity['status'] == 'pending' and not op.progress.get('role_assigned'):
                self.platform.call('PUT', f"/roles/users/{identity['id']}/role", json={'role_id': role['id']})
                op.checkpoint(role_assigned=True)
            current = self.platform.record(employee_id)
            data = {**current['data'], 'employee_code': current['data']['identifier'], 'platform_user_id': identity['id']}
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': data})
            cases = self.platform.records(CASE, CASE_FIELDS)
            case = next((c for c in cases if c['data'].get('employee_id') == employee_id), None)
            if not case:
                case = self._create_once(op, 'case', CASE, dict(employee_id=employee_id, template_key='default_onboarding',
                    template_version=CURRENT_TEMPLATE_VERSION, hrms_operation_key=marker), actor.user_id, cases, marker)
            case_id = case['entity_id']
            state = self.platform.enroll(case_id, 'hrms_onboardingcase')
            tasks = self.platform.tasks(case_id)
            active_ids = {u['id'] for u in users if u['status'] == 'active'}
            current_role = {u['id']: u.get('role') for u in users}

            def holds(row, role):
                user_id = row['data'].get('platform_user_id')
                return user_id in active_ids and (current_role.get(user_id) or row['data'].get('hrms_role')) == role
            # Spread steps across the people in a role: whoever has the fewest open onboarding steps.
            load = Counter(t.get('assigned_to') for steps in self.platform.steps_by_case().values()
                           for t in steps if t['status'] not in DONE)

            def least_busy(role):
                people = sorted((r for r in rows if holds(r, role)),
                                key=lambda r: (load[r['data']['platform_user_id']], r['data'].get('employee_code') or ''))
                return people[0]['data']['platform_user_id'] if people else None
            manager = reporting_manager({'entity_id': employee_id, 'data': data}, rows)
            manager_id = manager['data']['platform_user_id'] if manager and manager['data']['platform_user_id'] in active_ids else None
            template = TEMPLATES[case['data'].get('template_version') or 1]
            for step in template:
                if (existing_step := task_for_step(tasks, step)):
                    if existing_step['status'] == 'NOT_STARTED':
                        self.platform.enroll(existing_step['id'], 'hrms_onboardingstep')
                    continue
                key = f'task_{step.sequence}_requested'
                if op.progress.get(key):
                    raise AppError(409, 'Task creation needs reconciliation before retrying')
                if step.assignee_role is None:
                    owner = identity['id']
                else:
                    # Nobody in the role (or no manager with a login): HR Full covers it, then whoever added the hire.
                    owner = ((manager_id if step.assignee_role == REPORTING_MANAGER else least_busy(step.assignee_role))
                             or least_busy('hrms_hr_full') or actor.user_id)
                load[owner] += 1
                op.checkpoint(**{key: True})
                step_row = self.platform.create_record('HRMS.OnboardingStep', {
                    'case_id': case_id, 'sequence': step.sequence,
                    'title': step.title, 'description': f'HRMS onboarding step {step.sequence}; template v1; created by {actor.user_id}.',
                    'assigned_to': owner, 'due_date': step.due_date(request.date_joined, datetime.now(UTC).date()).isoformat(),
                    'hrms_operation_key': f'{marker}:{step.sequence}'}, actor.user_id)
                self.platform.enroll(step_row['entity_id'], 'hrms_onboardingstep')
                tasks = self.platform.tasks(case_id)
            final = self.platform.record(employee_id)
            result = dict(employee=self.employee_item(final, rows), onboarding_entity_id=case_id,
                          onboarding_state=state, onboarding_task_count=len(template),
                          account_status=identity['status'], idempotent=False)
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

    def has_employee_profile(self, actor):
        """Whether the account is linked to exactly one employee, which self-service (leave) needs."""
        return sum(1 for r in self.employees() if r['data'].get('platform_user_id') == actor.user_id) == 1

    def own_employee(self, actor, rows):
        own = [r for r in rows if r['data'].get('platform_user_id') == actor.user_id]
        if len(own) != 1:
            raise AppError(403, 'Your account has no unique employee profile')
        return own[0]

    def leave(self, actor, view, limit, offset, state=None):
        employees = self.employees()
        own = self.own_employee(actor, employees)
        if view not in {'mine', 'approvals'}:
            raise AppError(400, 'view must be mine or approvals')
        by_id = {e['entity_id']: e for e in employees}
        names = {key: name(e) for key, e in by_id.items()}
        states = self.platform.states('hrms_leaverequest')
        keys = custom_keys(self.platform, LEAVE)
        rows = [r for r in self.platform.records(LEAVE, LEAVE_FIELDS + keys) if r['data'].get('employee_id') in by_id]
        if view == 'mine':
            rows = [r for r in rows if r['data']['employee_id'] == own['entity_id']]
        else:
            approvers = LeaveApprovers(self.platform, employees)
            rows = [r for r in rows if r['data']['employee_id'] != own['entity_id'] and actor.user_id in approvers(
                by_id[r['data']['employee_id']], r['data']['start_date'], r['data']['end_date'])]
        if state:
            rows = [r for r in rows if states.get(r['entity_id'], 'not_enrolled') == state]
        rows.sort(key=lambda r: r['data']['start_date'], reverse=True)  # Newest first, so limits keep the current ones.
        from .wfh import WfhService
        wfh = WfhService(self)
        calendars = wfh.holiday_calendars()
        holidays = lambda r: wfh.holiday_dates(by_id[r['data']['employee_id']]['data'].get('work_location'), calendars)
        return [dict(entity_id=r['entity_id'], identifier=r['data'].get('identifier') or '',
                     employee_name=names[r['data']['employee_id']], start_date=r['data']['start_date'],
                     end_date=r['data']['end_date'], leave_type=r['data']['leave_type'], reason=r['data'].get('reason'),
                     custom=custom_values(r['data'], keys),
                     days=leave_days(r['data']['start_date'], r['data']['end_date'], holidays(r)),
                     state=states.get(r['entity_id'], 'not_enrolled')) for r in rows[offset:offset + limit]]

    def create_leave(self, actor, request):
        require(actor, 'leave:create')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'leave:{request.idempotency_key}', fingerprint(request))
            if op.result:
                return {**op.result, 'idempotent': True}
            employees = self.employees()
            own = self.own_employee(actor, employees)
            self._check_leave_form(actor, request.model_dump(mode='json', exclude={'idempotency_key', 'custom'}))
            custom = check_custom(self.platform, LEAVE, request.custom)
            started = (datetime.now(UTC).date() - request.start_date).days
            if started > 0 and (request.leave_type != 'sick' or started > SICK_LEAVE_BACKDATE_DAYS):
                # Leave is planned ahead; only sick leave is recorded after it began, within a week.
                raise AppError(422, f'Leave must start today or later; sick leave can be recorded up to '
                                    f'{SICK_LEAVE_BACKDATE_DAYS} days after it began')
            start, end = request.start_date.isoformat(), request.end_date.isoformat()
            if not LeaveApprovers(self.platform, employees)(own, start, end):
                raise AppError(400, 'Nobody can approve this leave: you have no project manager for these dates, '
                                    'no linked reporting manager, and no HR Full account is active')
            manager = reporting_manager(own, employees)
            marker = hashlib.sha256(f'{actor.organization_id}:{actor.user_id}:leave:{request.idempotency_key}'.encode()).hexdigest()
            rows = self.platform.records(LEAVE, LEAVE_FIELDS)
            from .wfh import WfhService
            wfh = WfhService(self)
            if not leave_days(request.start_date.isoformat(), request.end_date.isoformat(), wfh.holiday_dates(own['data'].get('work_location'))):
                raise AppError(422, 'These dates are only weekends or published holidays; choose at least one working day')
            wfh.check_leave_conflict(db, actor, own['entity_id'], request.start_date, request.end_date)
            states = self.platform.states('hrms_leaverequest')
            for row in rows:
                d = row['data']
                if d.get('hrms_operation_key') == marker:
                    continue
                # Any state but rejected or cancelled holds the dates, including steps added in Settings.
                if (d.get('employee_id') == own['entity_id'] and states.get(row['entity_id'], 'pending') not in {'rejected', 'cancelled'}
                    and d['start_date'] <= request.end_date.isoformat() and d['end_date'] >= request.start_date.isoformat()):
                    raise AppError(409, 'A pending or approved leave request overlaps these dates')
            data = {**request.model_dump(mode='json', exclude={'idempotency_key', 'custom'}), **custom}
            data.update(employee_id=own['entity_id'], manager_id=manager['entity_id'] if manager else None,
                        hrms_operation_key=marker)
            row = self._create_once(op, 'leave', LEAVE, data, actor.user_id, rows, marker)
            state = self.platform.enroll(row['entity_id'], 'hrms_leaverequest')
            result = dict(entity_id=row['entity_id'], identifier=row['data'].get('identifier') or '', state=state, idempotent=False)
            self.journal.audit(db, actor, 'leave.created', row['entity_id'])
            op.finish(result)
            return result

    def _check_leave_form(self, actor, data):
        """The tenant's leave form, enforced on the server: required fields and configured leave types.
        Only fields the employee submits are checked; HRMS fills in employee_id and manager_id."""
        from .form_config import form_configuration
        for field in form_configuration(self.platform, actor, LEAVE)['fields']:
            key = field['field']
            if key not in data:
                continue
            label = field.get('description') or key.replace('_', ' ').capitalize()
            if field.get('required') and data[key] in (None, ''):
                raise AppError(422, f'{label} is required')
            options = field.get('enum_values')
            if options and data[key] not in (None, '') and data[key] not in options:
                raise AppError(422, f'{label} must be one of the configured options')

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
        approver = not own and actor.user_id in LeaveApprovers(self.platform, employees)(
            owner, row['data']['start_date'], row['data']['end_date'])
        if not own and not approver:
            raise AppError(404, 'Leave request was not found')
        state = self.platform.states('hrms_leaverequest').get(entity_id)
        # Approvers decide whatever their role: a project or reporting manager who is also an
        # admin or HR would otherwise leave the request undecidable.
        if state == 'pending':
            allowed = ['cancel'] if own else ['approve', 'reject']
        elif state == 'approved' and own and row['data']['start_date'] > date.today().isoformat():
            # Approved leave can be cancelled until the day it starts, on a workflow version that
            # has that step: leave enrolled before the step existed keeps its original rules.
            allowed = ['cancel']
        else:
            allowed = []
        # Offer each step under the name Settings → Funnels gives it, and not at all if it was removed.
        offered = self._offered(entity_id, allowed) if allowed else {}
        return dict(entity_id=entity_id, current_state=state, available_transitions=[
            dict(trigger=t, label=offered[t], allowed=True) for t in allowed if t in offered])

    def _offered(self, entity_id, triggers):
        """HRMS leave steps the current state offers, each with its configured label."""
        from .workflow_config import step_targets
        available = self.platform.call('GET', f'/entities/{entity_id}/transitions/available')
        state, options = available.get('current_state'), available.get('available_transitions', [])
        result = {}
        for trigger in triggers:
            match = next((t for t in options if t['trigger'] == trigger or t.get('to_state') in step_targets(LEAVE, state, trigger)), None)
            if match:
                result[trigger] = match.get('label') or trigger.title()
        return result

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
