from native_permissions import grants
"""HRMS keeps working when an organization renames or adds workflow steps in Settings → Funnels."""
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest

from hrms_app.errors import AppError
from hrms_app.extra_steps import ExtraSteps, hrms_step
from hrms_app.platform import Actor, PlatformClient
from hrms_app.workflow_config import offers_step

LEAVE = 'HRMS.LeaveRequest'


def client(available, refused=('approve',)):
    """A platform where the leave's 'approve' step was renamed 'manager_approve'."""
    sent = []

    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json=available)
        trigger = __import__('json').loads(request.content)['trigger']
        sent.append(trigger)
        return httpx.Response(400 if trigger in refused else 200, json={'detail': 'Unknown trigger'} if trigger in refused else {})
    c = PlatformClient('http://platform.test', 'org', 'svc@example.com', 'secret', transport=httpx.MockTransport(handle))
    c.service_token = lambda: 'token'
    return c, sent


PENDING = {'current_state': 'pending', 'available_transitions': [
    {'trigger': 'manager_approve', 'to_state': 'approved'}, {'trigger': 'reject', 'to_state': 'rejected'},
    {'trigger': 'cancel', 'to_state': 'cancelled'}, {'trigger': 'send_to_hr', 'to_state': 'hr_review'}]}


def test_a_renamed_step_is_run_under_its_new_trigger():
    c, sent = client(PENDING)
    c.call('POST', '/entities/leave-1/transitions', json={'entity_id': 'leave-1', 'trigger': 'approve', 'idempotency_key': 'k-1'})
    assert sent == ['approve', 'manager_approve']


def test_other_refusals_stand():
    c, sent = client(PENDING, refused=('reject',))
    with pytest.raises(AppError):  # 'reject' exists: the platform refused it for its own reasons
        c.call('POST', '/entities/leave-1/transitions', json={'entity_id': 'leave-1', 'trigger': 'reject', 'idempotency_key': 'k-2'})
    assert sent == ['reject']


def test_renamed_steps_still_count_as_available_and_added_ones_are_told_apart():
    assert offers_step(LEAVE, 'pending', 'approve', PENDING['available_transitions'])
    assert not offers_step(LEAVE, 'approved', 'approve', PENDING['available_transitions'])
    added = [t['trigger'] for t in PENDING['available_transitions'] if not hrms_step(LEAVE, 'pending', t)]
    assert added == ['send_to_hr']
    assert not hrms_step(LEAVE, 'hr_review', {'trigger': 'approve', 'to_state': 'approved'})  # out of an added state


class Journal:
    def __init__(self):
        self.ops = {}

    @contextmanager
    def lock(self, org):
        yield None

    def operation(self, db, who, key, payload):
        op = self.ops.setdefault(key, SimpleNamespace(result=None))
        op.finish = lambda result: setattr(op, 'result', result)
        return op

    def audit(self, *args):
        pass


class Platform:
    def __init__(self):
        self.sent = []

    def record(self, entity_id):
        return {'entity_type_id': 'type-perf', 'data': {}}

    def call(self, method, path, **kwargs):
        if path == '/entity-types':
            return {'items': [{'entity_type_id': 'type-perf', 'name': 'HRMS.PerformanceReview'}]}
        if method == 'GET':
            return {'current_state': 'manager_review', 'available_transitions': [
                {'trigger': 'submit_manager', 'to_state': 'calibration'},
                {'trigger': 'skip_level_review', 'label': 'Skip-level review', 'to_state': 'skip_level'}]}
        self.sent.append(kwargs['json']['trigger'])


def steps(platform=None):
    platform = platform or Platform()
    return ExtraSteps(SimpleNamespace(platform=platform, journal=Journal(), employees=lambda: [])), platform


def test_added_steps_are_offered_to_the_people_who_manage_the_record():
    service, platform = steps()
    hr = Actor('hr', 'org', '', frozenset({'hrms_hr_full'}), grants({'hrms_hr_full'}))
    assert service.available(hr, 'review-1')['steps'] == [{'trigger': 'skip_level_review', 'label': 'Skip-level review', 'to_state': 'skip_level'}]
    service.run(hr, 'review-1', 'skip_level_review', 'step-key-1')
    assert platform.sent == ['skip_level_review']
    employee = Actor('emp', 'org', '', frozenset({'hrms_employee'}), grants({'hrms_employee'}))
    assert service.available(employee, 'review-1')['steps'] == []
    with pytest.raises(AppError):
        service.run(employee, 'review-1', 'skip_level_review', 'step-key-2')
    with pytest.raises(AppError):  # HRMS's own steps keep their own rules and screens
        service.run(hr, 'review-1', 'submit_manager', 'step-key-3')
