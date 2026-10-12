from native_permissions import grants
from contextlib import contextmanager

import pytest

from hrms_app.errors import AppError
from hrms_app.onboarding_template import DEFAULT_ONBOARDING_STEPS
from hrms_app.platform import Actor
from hrms_app.service import HrmsService, task_for_step


def actor(user, role='hrms_employee'):
    return Actor(user, 'org', 'token', frozenset({role}), grants({role}))


class Journal:
    @contextmanager
    def lock(self, org):
        yield None

    def audit(self, *args):
        pass


class Platform:
    def __init__(self):
        self.state = 'in_progress'
        self.items = [dict(id=str(s.sequence), stage=f'onboarding-step-{s.sequence}', status='OPEN',
                           assigned_to='owner', due_date=None) for s in DEFAULT_ONBOARDING_STEPS]
        self.writes = []

    def records(self, kind, fields):
        if kind == 'HRMS.Employee':
            return [dict(entity_id='employee', data=dict(first_name='Test', last_name='Employee', employee_code='EMP-1'))]
        return [dict(entity_id='case', data=dict(employee_id='employee', template_key='default_onboarding', template_version=1))]

    def tasks(self, entity_id):
        return self.items

    def steps_by_case(self):
        return {'case': self.items}

    def states(self, machine):
        return {'case': self.state}

    def users(self):
        return [dict(id='owner', full_name='Assigned Owner')]

    def call(self, method, path, **kwargs):
        self.writes.append((method, path))
        if path != '/entities/case/transitions':
            next(t for t in self.items if t['id'] == path.split('/')[2])['status'] = 'COMPLETED'
        else:
            self.state = 'completed'


def test_assignee_can_complete_ready_step_through_native_transition_api():
    api = Platform()
    service = HrmsService(api, Journal(), 'newtuple.com')
    result = service.complete_step(actor('owner'), 'case', 1)
    assert result['completed_steps'] == 1
    assert result['steps'][2]['can_complete']
    assert api.writes == [('POST', '/entities/1/transitions')]


def test_prerequisite_and_assignment_are_enforced():
    api = Platform()
    service = HrmsService(api, Journal(), 'newtuple.com')
    with pytest.raises(AppError) as error:
        service.complete_step(actor('owner'), 'case', 3)
    assert error.value.status == 409
    with pytest.raises(AppError) as error:
        service.complete_step(actor('other'), 'case', 1)
    assert error.value.status == 404
    assert not api.writes


def test_final_transition_requires_hr_and_all_steps_complete():
    api = Platform()
    service = HrmsService(api, Journal(), 'newtuple.com')
    with pytest.raises(AppError):
        service.complete_case(actor('owner'), 'case')
    with pytest.raises(AppError):
        service.complete_case(actor('hr', 'hrms_hr_full'), 'case')
    for task in api.items:
        task['status'] = 'COMPLETED'
    assert service.complete_case(actor('hr', 'hrms_hr_full'), 'case')['state'] == 'completed'
    assert api.writes == [('POST', '/entities/case/transitions')]


def test_new_api_tasks_and_existing_native_tasks_use_same_template():
    step = DEFAULT_ONBOARDING_STEPS[0]
    assert task_for_step([{'id': '1', 'description': 'HRMS onboarding step 1; template v1;'}], step)['id'] == '1'
    with pytest.raises(AppError):
        task_for_step([{'stage': 'onboarding-step-1'}, {'description': 'HRMS onboarding step 1; template v1;'}], step)


def test_steps_say_whether_they_are_assigned_to_the_reader():
    # HR can complete any ready step, but only its owner's My Work counts it as waiting on them.
    service = HrmsService(Platform(), Journal(), 'newtuple.com')
    hr_steps = service.onboarding(actor('hr-user', 'hrms_hr_full'))[0]['steps']
    owner_steps = service.onboarding(actor('owner'))[0]['steps']
    assert hr_steps[0]['can_complete'] and not hr_steps[0]['assigned_to_me']
    assert owner_steps[0]['can_complete'] and owner_steps[0]['assigned_to_me']


def test_api_response_models_carry_the_fields_my_work_reads():
    # Service tests bypass FastAPI's response models, which drop any field they do not declare.
    from hrms_app.responses import LeaveListItem, OnboardingStepItem
    assert 'assigned_to_me' in OnboardingStepItem.model_fields
    assert 'days' in LeaveListItem.model_fields


class BrokenCasePlatform(Platform):
    """The working case plus one that cannot be read."""

    def __init__(self, broken):
        super().__init__()
        self.broken = broken

    def records(self, kind, fields):
        rows = super().records(kind, fields)
        if kind == 'HRMS.Employee':
            return rows
        bad = dict(entity_id='bad', data=dict(employee_id='employee', template_key='default_onboarding', template_version=1))
        if self.broken == 'template':
            bad['data']['template_version'] = 99
        if self.broken == 'employee':
            bad['data']['employee_id'] = 'deleted'
        return rows + [bad]

    def steps_by_case(self):
        duplicate = self.items + [dict(self.items[0], id='dup')] if self.broken == 'duplicate' else self.items
        return {'case': self.items, 'bad': duplicate}

    def states(self, machine):
        return {'case': self.state, 'bad': 'in_progress'}


@pytest.mark.parametrize('broken', ['template', 'employee', 'duplicate'])
def test_one_unreadable_case_does_not_hide_the_others(broken):
    service = HrmsService(BrokenCasePlatform(broken), Journal(), 'newtuple.com')
    assert [c['entity_id'] for c in service.onboarding(actor('hr', 'hrms_hr_full'))] == ['case']
    with pytest.raises(AppError) as error:
        service.onboarding(actor('hr', 'hrms_hr_full'), 'bad')
    assert error.value.status == 409


def test_step_due_dates_follow_the_joining_date():
    from datetime import date
    by_key = {s.key: s for s in DEFAULT_ONBOARDING_STEPS}
    today, joining = date(2026, 10, 9), date(2026, 11, 2)
    due = lambda key, joined=joining: by_key[key].due_date(joined, today).date().isoformat()
    # Pre-boarding is ready by day one; first-week work counts from the joining date.
    assert [due(k) for k in ('newtuple_id', 'razorpay_account', 'hrms_invitation', 'asset_allocation')] == ['2026-11-02'] * 4
    assert [due(k) for k in ('employee_profile', 'documents', 'hr_orientation', 'pm_allocation')] == \
        ['2026-11-05', '2026-11-05', '2026-11-07', '2026-11-09']
    # A hire added after they joined counts from today instead of from a date already past.
    assert due('newtuple_id', date(2026, 9, 1)) == '2026-10-09' and due('hr_orientation', date(2026, 9, 1)) == '2026-10-14'
    assert by_key['newtuple_id'].due_date(joining, today).hour == 12
