"""Onboarding goes to the right people, and HR can reassign, re-date, skip or cancel it."""
from datetime import date

import pytest

from hrms_app.errors import AppError
from hrms_app.onboarding_template import TEMPLATES
from hrms_app.service import HrmsService
from test_employee_access import Journal as AccessJournal
from test_employee_access import ProvisioningPlatform, employee_request
from test_onboarding import Journal, Platform, actor

HR = actor('hr', 'hrms_hr_full')


def staff(platform, key, code, role, manager=None):
    platform.rows[key] = dict(entity_id=key, kind='HRMS.Employee', data=dict(
        first_name=key.title(), last_name='Staff', employee_code=code, platform_user_id=f'{key}-user',
        hrms_role=role, employment_status='active', reports_to_employee_code=manager))


def test_steps_go_to_the_least_busy_owner_and_the_hires_own_manager():
    p = ProvisioningPlatform(existing=True)
    for key, code, role in (('busy', 'OA1', 'hrms_office_admin'), ('free', 'OA2', 'hrms_office_admin'),
                            ('lead', 'M1', 'hrms_manager'), ('people', 'HR1', 'hrms_hr_full')):
        staff(p, key, code, role)
    p.rows['old-step'] = dict(entity_id='old-step', kind='HRMS.OnboardingStep', data=dict(case_id='another-hire', sequence=1, assigned_to='busy-user'))
    accounts = p.users()
    p.users = lambda: accounts + [dict(id=f'{k}-user', status='active', role=None) for k in ('busy', 'free', 'lead', 'people')]
    result = HrmsService(p, AccessJournal(), 'newtuple.com').create_employee(
        actor('hr', 'hrms_hr_full'), employee_request(reports_to_entity_id='lead'))
    owners = {r['data']['sequence']: r['data']['assigned_to'] for r in p.rows.values()
              if r['kind'] == 'HRMS.OnboardingStep' and r['entity_id'] != 'old-step'}
    assert result['onboarding_task_count'] == len(TEMPLATES[2]) == 9
    assert owners[1] == 'free-user'          # the other office admin already has an open step
    assert owners[9] == 'lead-user'          # the hire's own manager welcomes them
    assert owners[2] == owners[3] == 'people-user'  # nobody in Finance: HR Full covers it, not the creator


class ManagedPlatform(Platform):
    """A version-two case for HR to manage; records and transitions are kept in memory."""

    def __init__(self):
        super().__init__()
        self.items.append(dict(id='9', stage='onboarding-step-9', status='OPEN', assigned_to='owner', due_date=None))
        self.data = {t['id']: {} for t in self.items}
        self.case = dict(employee_id='employee', template_key='default_onboarding', template_version=2)

    def records(self, kind, fields):
        if kind == 'HRMS.OnboardingCase':
            return [dict(entity_id='case', data=self.case)]
        return super().records(kind, fields)

    def users(self):
        return [dict(id='owner', full_name='Assigned Owner', status='active'),
                dict(id='deputy', full_name='Deputy', status='active')]

    def record(self, key):
        return dict(entity_id=key, data=self.case if key == 'case' else {**self.data[key]})

    def call(self, method, path, **kwargs):
        self.writes.append((method, path))
        key = path.split('/')[2]
        if method == 'PUT' and key == 'case':
            self.case = kwargs['json']['data']
        elif method == 'PUT':
            task = next(t for t in self.items if t['id'] == key)
            task.update({k: v for k, v in kwargs['json']['data'].items() if k in {'assigned_to', 'due_date'}})
        elif kwargs['json']['trigger'] == 'cancel':
            next(t for t in self.items if t['id'] == key)['status'] = 'CANCELLED'
        else:
            super().call(method, path, **kwargs)


def service(platform):
    return HrmsService(platform, Journal(), 'newtuple.com')


def test_hr_can_hand_a_step_to_someone_else_and_move_its_date():
    p = ManagedPlatform()
    case = service(p).update_step(HR, 'case', 6, 'deputy', date(2026, 11, 2))
    step = case['steps'][5]
    assert step['owner_name'] == 'Deputy' and step['due_date'].startswith('2026-11-02')
    with pytest.raises(AppError):
        service(p).update_step(HR, 'case', 6, 'stranger', None)
    with pytest.raises(AppError):
        service(p).update_step(actor('owner'), 'case', 6, 'deputy', None)


def test_a_skipped_step_no_longer_holds_up_the_steps_after_it():
    p = ManagedPlatform()
    service(p).complete_step(HR, 'case', 1)
    case = service(p).skip_step(HR, 'case', 3, 'Joins as a contractor; no HRMS account')
    assert case['steps'][2]['readiness'] == 'skipped'
    assert case['steps'][3]['readiness'] == 'ready'   # personal details waited on step 3
    assert case['completed_steps'] == 2 and case['total_steps'] == 9


def test_cancelling_onboarding_cancels_its_open_steps():
    p = ManagedPlatform()
    case = service(p).cancel_onboarding(HR, 'case', 'Offer withdrawn')
    assert case['state'] == 'cancelled' and case['cancel_reason'] == 'Offer withdrawn'
    assert all(t['status'] == 'CANCELLED' for t in p.items)
    assert not case['can_complete_case'] and not any(s['can_complete'] or s['can_manage'] for s in case['steps'])


def test_version_one_cases_keep_their_eight_steps():
    case = service(Platform()).onboarding(HR)[0]
    assert case['total_steps'] == 8
