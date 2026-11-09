"""HRMS composition and business rules over the native platform HTTP API."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hashlib
import secrets

from .form_values import editable_values
from .custom_fields import check_custom, custom_keys, custom_values
from .errors import AppError
from .form_config import active_workflow, configured_form
from .employee_access import identity_roles
from .policy import capabilities, require, projected_records

EMPLOYEE = 'HRMS.Employee'
LEAVE = 'HRMS.LeaveRequest'
ALLOCATION_FIELDS = ['project_id', 'employee_id', 'start_date', 'end_date']
LIVE_ALLOCATION = {'planned', 'active'}
EMPLOYEE_FIELDS = ['identifier', 'employee_code', 'first_name', 'last_name', 'work_email',
                   'department', 'designation', 'employment_status', 'reports_to_employee_code',
                   'platform_user_id', 'hrms_role', 'employment_type', 'date_joined', 'work_location',
                   'notice_period_days', 'phone', 'last_working_day', 'exit_reason', 'exit_note',
                   'hrms_operation_key']
OFFBOARDED = 'offboarded'
LEAVE_FIELDS = ['identifier', 'employee_id', 'manager_id', 'start_date', 'end_date',
                'leave_type', 'reason', 'hrms_operation_key']
SICK_LEAVE_BACKDATE_DAYS = 7


def fingerprint(request):
    """A request as its idempotency record sees it. No custom fields means the same request as before
    custom fields existed, so a retry sent across that deploy still matches."""
    payload = request.model_dump(mode='json')
    if not payload.get('custom'):
        payload.pop('custom', None)
    return payload


def name(row):
    return f"{row['data'].get('first_name', '')} {row['data'].get('last_name', '')}".strip()


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
        rows = self.platform.records(EMPLOYEE, EMPLOYEE_FIELDS + keys, token=actor.token)
        users = {}
        users_readable = True
        try:
            users = {u['id']: u for u in self.platform.users(token=actor.token)}
        except AppError as exc:
            if exc.status != 403:
                raise
            users_readable = False
        from .employee_work import employee_enrollments
        workflow_states = {}
        workflow_access = True
        try:
            for enrollment in employee_enrollments(self.platform, actor):
                if not enrollment.get('archived_at'):
                    workflow_states.setdefault(enrollment['entity_id'], []).append(enrollment['current_state'])
        except AppError as exc:
            if exc.status != 403:
                raise
            workflow_access = False
        result = []
        for row in rows:
            item = self.employee_item(row, rows, keys)
            user = users.get(row['data'].get('platform_user_id'))
            if user and user.get('role'):
                item['role'] = user['role']  # Current role; the employee record keeps the role it was created with.
            item['account_status'] = user['status'] if user else ('not_linked' if users_readable else 'unknown')
            item['uses_google_sign_in'] = bool(user and user.get('auth_type') == 'google')
            item['can_setup_access'] = bool(user and user.get('organization_id') == actor.organization_id
                and user['status'] in {'pending', 'active'} and item['employment_status'] == 'active'
                and 'employee:activate' in capabilities(actor)
                and bool(identity_roles(self.platform, actor, user)))
            item['onboarding_state'] = ' · '.join(workflow_states.get(row['entity_id'], [])) or None
            item['onboarding_status_message'] = 'No visible workflow' if workflow_access else 'Workflow access restricted'
            result.append(item)
        return sorted(result, key=lambda r: r['full_name'].casefold())

    def form_options(self, actor):
        require(actor, 'employee:create')
        fields = {f['field']: f for f in configured_form(self.platform, EMPLOYEE)['fields']}
        # Native roles are the catalog; internal service identities are never employee roles.
        native_roles = self.platform.call('GET', '/roles')
        native_roles = [r for r in native_roles if r['name'] not in {'hrms_application_service', 'hrms_onboarding_employee'}]
        roles = [r['name'] for r in native_roles]
        role_labels = {r['name']: r['display_name'] for r in native_roles}
        return dict(departments=fields.get('department', {}).get('enum_values') or [],
                    designations=fields.get('designation', {}).get('enum_values') or [],
                    department_labels=fields.get('department', {}).get('enum_labels') or {},
                    designation_labels=fields.get('designation', {}).get('enum_labels') or {},
                    roles=roles, role_labels=role_labels)


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
        payload = request.model_dump(mode='json', exclude_unset=True)
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee-update:{request.idempotency_key}', {**payload, 'employee_id': employee_id})
            if op.result:
                return op.result
            rows = self.employees()
            employee = self._editable_employee(rows, employee_id)
            record = self.platform.record(employee_id, token=actor.token)
            custom = check_custom(self.platform, EMPLOYEE, request.custom, record['data'])
            supplied = {k:v for k,v in payload.items() if k not in {'idempotency_key','reports_to_entity_id','custom'}}
            patch = editable_values(self.platform, EMPLOYEE, supplied, current=record['data'],
                excluded={'employee_code','employment_status','platform_user_id','hrms_role','last_working_day','exit_reason','exit_note','work_email','reports_to_employee_code', *custom})
            data = {**record['data'], **patch, **custom}
            if 'reports_to_entity_id' in payload:
                manager = self._check_reporting_manager(rows, employee, request.reports_to_entity_id)
                relationship = {'reports_to_employee_code': manager['data'].get('employee_code') if manager else None}
                editable_values(self.platform, EMPLOYEE, relationship, current=record['data'],
                    excluded={f['field'] for f in configured_form(self.platform, EMPLOYEE)['fields'] if f['field']!='reports_to_employee_code'})
                data.update(relationship)
            self.platform.call('PUT', f'/entity-records/{employee_id}', token=actor.token, json={'data': {k:v for k,v in data.items() if record['data'].get(k)!=v}})
            self.journal.audit(db, actor, 'employee.updated', employee_id)
            result = self.employee_item(self.platform.record(employee_id, token=actor.token), list(projected_records(self.platform, actor, EMPLOYEE, EMPLOYEE_FIELDS).values()), list(custom))
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
            employee = (next((row for row in rows if row['entity_id'] == employee_id), None)
                        if op.progress.get('exit_record_saved') else self._editable_employee(rows, employee_id))
            if employee is None:
                raise AppError(404, 'Employee was not found')
            joined = employee['data'].get('date_joined')
            never_joined = request.reason == 'did_not_join'
            if joined and not never_joined and request.last_working_day.isoformat() < str(joined)[:10]:
                raise AppError(400, 'The last working day cannot be before the joining date')
            user_id = employee['data'].get('platform_user_id')
            identity = next((u for u in self.platform.users(token=actor.token) if u['id'] == user_id), None) if user_id else None
            leaving = never_joined or request.last_working_day <= datetime.now(UTC).date()
            record = self.platform.record(employee_id, token=actor.token)['data']
            editable_values(self.platform, EMPLOYEE, {k:v for k,v in request.model_dump(mode='json',exclude_unset=True).items() if k!='idempotency_key'}, current={'last_working_day':record.get('last_working_day'),'reason':record.get('exit_reason'),'note':record.get('exit_note')}, aliases={'exit_reason':'reason','exit_note':'note'}, excluded={f['field'] for f in configured_form(self.platform, EMPLOYEE)['fields'] if f['field'] not in {'last_working_day','exit_reason','exit_note'}})
            # Completing a notice period without a new note keeps the note recorded with the resignation.
            data = {**record, 'last_working_day': payload['last_working_day'],
                    'exit_reason': request.reason, 'exit_note': request.note or record.get('exit_note'),
                    'employment_status': OFFBOARDED if leaving else 'active'}
            self.platform.call('PUT', f'/entity-records/{employee_id}', token=actor.token, json={'data': {k: v for k, v in data.items() if k in {'last_working_day', 'exit_reason', 'exit_note', 'employment_status'}}})
            op.checkpoint(exit_record_saved=True)
            if leaving and identity and identity['status'] in {'active', 'pending'}:
                self._end_access(op, user_id, identity['status'], token=actor.token)
            self.journal.audit(db, actor, 'employee.offboarded' if leaving else 'employee.notice_recorded', employee_id)
            result = self.employee_item(self.platform.record(employee_id, token=actor.token), list(projected_records(self.platform, actor, EMPLOYEE, EMPLOYEE_FIELDS).values()))
            op.finish(result)
            return result

    def _end_access(self, op, user_id, status, *, token):
        """Suspend the leaver's membership here; an invite never activated is also rejected so it
        cannot be approved later. A retry tolerates steps the interrupted attempt already did."""
        retry = op.progress.get('suspend_requested')
        op.checkpoint(suspend_requested=True)
        steps = ['suspend'] + (['reject'] if status == 'pending' else [])
        for step in steps:
            try:
                self.platform.call('POST', f'/users/{user_id}/{step}', token=token)
            except AppError as exc:
                if exc.status in {401, 403} or not retry:
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
            data = {**self.platform.record(employee_id, token=actor.token)['data'], 'last_working_day': None, 'exit_reason': None, 'exit_note': None}
            self.platform.call('PUT', f'/entity-records/{employee_id}', token=actor.token, json={'data': {k: v for k, v in data.items() if k in {'last_working_day', 'exit_reason', 'exit_note', 'employment_status'}}})
            self.journal.audit(db, actor, 'employee.exit_withdrawn', employee_id)
            result = self.employee_item(self.platform.record(employee_id, token=actor.token), list(projected_records(self.platform, actor, EMPLOYEE, EMPLOYEE_FIELDS).values()))
            op.finish(result)
            return result

    def create_employee(self, actor, request):
        require(actor, 'employee:create')
        payload = fingerprint(request)
        if request.role not in self.form_options(actor)['roles']:
            raise AppError(403, 'You cannot assign the requested employee role')
        from .form_config import registration_form
        registration = registration_form(self.platform)
        if 'work_email' not in {f['field'] for f in registration['fields']}:
            if request.work_email:
                raise AppError(422, 'Work email is entered in the configured Email Setup step')
            return self.register_employee(actor, request, registration)
        if not request.work_email:
            raise AppError(422, 'Work email is required by the registration form')
        email = str(request.work_email).lower().strip()
        if email.rsplit('@', 1)[-1] != self.domain:
            raise AppError(400, f'Work email must be on @{self.domain}')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee:{request.idempotency_key}', payload)
            if op.result:
                return {**op.result, 'idempotent': True}
            machine = op.progress.get('employee_workflow')
            if not machine:
                workflow = active_workflow(self.platform, EMPLOYEE)
                if workflow is None:
                    raise AppError(409, 'Publish and activate an Employee workflow in Settings before adding employees')
                machine = workflow['machine_name']
                op.checkpoint(employee_workflow=machine)
            rows = self.employees()
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
            data = {k: v for k, v in request.model_dump(mode='json', exclude_unset=True).items() if k not in {'idempotency_key', 'reports_to_entity_id', 'role', 'custom'}}
            data = editable_values(self.platform, EMPLOYEE, data, excluded={'employee_code','employment_status','platform_user_id','hrms_role','last_working_day','exit_reason','exit_note','reports_to_employee_code', *request.custom})
            data.update(check_custom(self.platform, EMPLOYEE, request.custom))
            data.update(work_email=email, employment_status='active', hrms_role=request.role,
                        reports_to_employee_code=manager['data'].get('employee_code') if manager else None,
                        hrms_operation_key=marker)
            if not existing:
                existing = self._create_once(op, 'employee', EMPLOYEE, data, actor.user_id, rows, marker, token=actor.token)
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
            data = {'employee_code': current['data']['identifier'], 'platform_user_id': identity['id']}
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': data})
            # Enrol only after the native account and employee links are complete, so
            # initial-state actions can use the final employee data. Keep retries on
            # the originally selected machine, even if Settings changes meanwhile.
            if not op.progress.get('employee_enrolled'):
                if op.progress.get('employee_enrollment_requested'):
                    state = self.platform.states(machine).get(employee_id)
                    if state is None:
                        raise AppError(409, 'Employee workflow enrollment outcome is uncertain; reconciliation is required')
                else:
                    op.checkpoint(employee_enrollment_requested=True)
                    state = self.platform.enroll(employee_id, machine, token=actor.token)
                op.checkpoint(employee_enrolled=True, employee_workflow_state=state)
            final = self.platform.record(employee_id, token=actor.token)
            visible_rows = list(projected_records(self.platform, actor, EMPLOYEE, EMPLOYEE_FIELDS).values())
            result = dict(employee=self.employee_item(final, visible_rows),
                          workflow=dict(machine_name=machine, current_state=op.progress['employee_workflow_state']),
                          account_status=identity['status'], idempotent=False)
            self.journal.audit(db, actor, 'employee.created', employee_id)
            op.finish(result)
            return result

    def register_employee(self, actor, request, registration):
        """Create only the Employee; the configured later state provisions its account."""
        from .custom_fields import _typed
        workflow = active_workflow(self.platform, EMPLOYEE)
        if workflow is None:
            raise AppError(409, 'Publish an Employee workflow before registering employees')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'employee:{request.idempotency_key}', fingerprint(request))
            if op.result:
                return {**op.result, 'idempotent': True}
            rows = self.employees()
            manager = next((r for r in rows if r['entity_id'] == request.reports_to_entity_id), None)
            if request.reports_to_entity_id and (not manager or manager['data'].get('employment_status') != 'active'):
                raise AppError(400, 'Reporting manager must be active in this organization')
            values = {**request.model_dump(mode='json', exclude_unset=True), **request.custom,
                      'hrms_role': request.role, 'reports_to_employee_code': manager['data'].get('employee_code') if manager else None}
            fields = {f['field']: f for f in registration['fields']}
            if set(request.custom) - set(fields):
                raise AppError(422, 'Fields are not on the registration form')
            data = {}
            for key, field in fields.items():
                if field.get('read_only') or key in {'employee_code','platform_user_id','employment_status'}:
                    continue
                value = values.get(key)
                if value in (None, ''):
                    if field.get('required'):
                        raise AppError(422, f"{field.get('description') or key} is required")
                    continue
                data[key] = _typed(field.get('description') or key, field, value)
            marker = hashlib.sha256(f'{actor.organization_id}:employee:{request.idempotency_key}'.encode()).hexdigest()
            data.update(hrms_role=request.role, employment_status='active', hrms_operation_key=marker)
            employee = self._create_once(op, 'employee', EMPLOYEE, data, actor.user_id, rows, marker, token=actor.token)
            employee_id = employee['entity_id']
            machine = op.progress.get('employee_workflow') or workflow['machine_name']
            op.checkpoint(employee_workflow=machine, employee_id=employee_id)
            current = self.platform.record(employee_id)
            self.platform.call('PUT', f'/entity-records/{employee_id}', json={'data': {'employee_code': current['data']['identifier']}})
            if not op.progress.get('employee_enrolled'):
                if op.progress.get('employee_enrollment_requested'):
                    state = self.platform.states(machine).get(employee_id)
                    if state is None:
                        raise AppError(409, 'Employee enrollment requires reconciliation')
                else:
                    op.checkpoint(employee_enrollment_requested=True)
                    state = self.platform.enroll(employee_id, machine, token=actor.token)
                op.checkpoint(employee_enrolled=True, employee_workflow_state=state)
            final = self.platform.record(employee_id, token=actor.token)
            visible_rows = list(projected_records(self.platform, actor, EMPLOYEE, EMPLOYEE_FIELDS).values())
            result = dict(employee=self.employee_item(final, visible_rows),
                          workflow=dict(machine_name=machine, current_state=op.progress['employee_workflow_state']),
                          account_status='not_created', idempotent=False)
            self.journal.audit(db, actor, 'employee.registered', employee_id)
            op.finish(result)
            return result

    def _create_once(self, op, key, entity_type, data, owner, rows, marker, *, token=None):
        existing = next((r for r in rows if r['data'].get('hrms_operation_key') == marker), None)
        if existing:
            return existing
        if op.progress.get(f'{key}_requested'):
            # A network timeout may follow a committed create. Do not blindly duplicate it.
            raise AppError(409, 'Creation outcome is uncertain; reconciliation is required')
        op.checkpoint(**{f'{key}_requested': True})
        try:
            return self.platform.create_record(entity_type, data, owner, **({"token": token} if token is not None else {}))
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
        readable_employees = projected_records(self.platform, actor, EMPLOYEE, EMPLOYEE_FIELDS)
        names = {key: name(e) for key, e in readable_employees.items()}
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
        readable = projected_records(self.platform, actor, LEAVE, LEAVE_FIELDS + keys)
        rows = [readable[r['entity_id']] for r in rows if r['entity_id'] in readable]
        return [dict(entity_id=r['entity_id'], identifier=r['data'].get('identifier') or '',
                     employee_name=names.get(r['data'].get('employee_id'), ''), start_date=r['data'].get('start_date'),
                     end_date=r['data'].get('end_date'), leave_type=r['data'].get('leave_type'), reason=r['data'].get('reason'),
                     custom=custom_values(r['data'], keys),
                     days=leave_days(r['data']['start_date'], r['data']['end_date'], holidays(r))
                          if all(r['data'].get(k) for k in ('start_date', 'end_date', 'employee_id')) else None,
                     state=states.get(r['entity_id'], 'not_enrolled')) for r in rows[offset:offset + limit]]

    def create_leave(self, actor, request):
        require(actor, 'leave:create')
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'leave:{request.idempotency_key}', fingerprint(request))
            if op.result:
                return {**op.result, 'idempotent': True}
            employees = self.employees()
            own = self.own_employee(actor, employees)
            editable_values(self.platform, LEAVE, request.model_dump(mode='json', exclude_unset=True, exclude={'idempotency_key','custom'}), excluded={'employee_id','manager_id', *request.custom})
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
            data = {**request.model_dump(mode='json', exclude_unset=True, exclude={'idempotency_key', 'custom'}), **custom}
            data.update(employee_id=own['entity_id'], manager_id=manager['entity_id'] if manager else None,
                        hrms_operation_key=marker)
            row = self._create_once(op, 'leave', LEAVE, data, actor.user_id, rows, marker, token=actor.token)
            state = self.platform.enroll(row['entity_id'], 'hrms_leaverequest', token=actor.token)
            result = dict(entity_id=row['entity_id'], identifier=row['data'].get('identifier') or '', state=state, idempotent=False)
            self.journal.audit(db, actor, 'leave.created', row['entity_id'])
            op.finish(result)
            return result

    def leave_actions(self, actor, entity_id):
        self.platform.record(entity_id, token=actor.token)
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
        offered = self._offered(entity_id, allowed, token=actor.token) if allowed else {}
        return dict(entity_id=entity_id, current_state=state, available_transitions=[
            dict(trigger=t, label=offered[t], allowed=True) for t in allowed if t in offered])

    def _offered(self, entity_id, triggers, *, token=None):
        """HRMS leave steps the current state offers, each with its configured label."""
        from .workflow_config import step_targets
        available = self.platform.call('GET', f'/entities/{entity_id}/transitions/available', token=token)
        state, options = available.get('current_state'), available.get('available_transitions', [])
        result = {}
        for trigger in triggers:
            match = next((t for t in options if t['trigger'] == trigger or t.get('to_state') in step_targets(LEAVE, state, trigger)), None)
            if match and match.get('allowed', False):
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
            result = self.platform.call('POST', f'/entities/{entity_id}/transitions', token=actor.token, json={
                'entity_id': entity_id, 'trigger': trigger,
                'idempotency_key': f'hrms:{actor.user_id}:{key}'})
            self.journal.audit(db, actor, f'leave.{trigger}.completed', entity_id)
            op.finish(result)
            return result
