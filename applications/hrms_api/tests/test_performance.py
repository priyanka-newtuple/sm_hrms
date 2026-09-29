from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.performance import CYCLE, REVIEW, GOAL, FEEDBACK, PerformanceService
from hrms_app.performance_contracts import Action
from hrms_app.platform import Actor


def actor(user, *roles):
    return Actor(user, 'org', '', frozenset(roles), frozenset())


class Platform:
    org = 'org'
    email = 'service@example.com'

    def __init__(self):
        self.rows = {}
        self.fail_trigger = None
        self.completed = set()

    def add(self, kind, data, state=None, entity_id=None):
        key = entity_id or f'record-{len(self.rows)}'
        self.rows[key] = dict(entity_id=key, organization_id='org', kind=kind, data=deepcopy(data),
                              state=state or pack_by_type(kind).initial_state)
        return self.rows[key]

    def records(self, kind, fields):
        return deepcopy([r for r in self.rows.values() if r['kind'] == kind])

    def states(self, machine):
        return {r['entity_id']: r['state'] for r in self.rows.values() if pack_by_type(r['kind']).machine_name == machine}

    def record(self, entity_id):
        return deepcopy(self.rows[entity_id])

    def create_record(self, kind, data, owner):
        return self.add(kind, data)

    def enroll(self, entity_id, machine):
        return self.rows[entity_id]['state']

    def call(self, method, path, **kwargs):
        data = kwargs['json']
        if method == 'PUT':
            self.rows[path.rsplit('/', 1)[1]]['data'] = deepcopy(data['data'])
            return
        if data['idempotency_key'] in self.completed:
            return
        if data['trigger'] == self.fail_trigger:
            self.fail_trigger = None
            raise AppError(503, 'Injected platform failure')
        row = self.rows[data['entity_id']]
        transitions = [t for t in pack_by_type(row['kind']).transitions if t[0] == row['state'] and t[1] == data['trigger']]
        assert len(transitions) == 1, (row['state'], data['trigger'])
        row['state'] = transitions[0][2]
        self.completed.add(data['idempotency_key'])


class Journal:
    def __init__(self):
        self.ops = {}
        self.audits = []

    @contextmanager
    def lock(self, org):
        yield self

    def operation(self, db, who, key, payload):
        if key in self.ops:
            result = self.ops[key]
            if result.actor != who.user_id or result.payload != payload:
                raise AppError(409, 'Idempotency conflict')
            return result
        op = SimpleNamespace(actor=who.user_id, payload=payload, result=None, progress={})
        op.checkpoint = lambda **values: op.progress.update(deepcopy(values))
        op.finish = lambda result: setattr(op, 'result', deepcopy(result))
        self.ops[key] = op
        return op

    def execute(self, sql, params):
        return SimpleNamespace(fetchone=lambda: next(((key,) for key, op in self.ops.items()
            if key != params[1] and op.result is None and 'performance_plan' in op.progress), None))

    def audit(self, db, who, action, target, operation_key=None):
        self.audits.append((who.user_id, action, target))


@pytest.fixture
def system():
    platform, journal = Platform(), Journal()
    service = PerformanceService(SimpleNamespace(platform=platform, journal=journal))
    participant = dict(employee_id='employee-record', employee_name='Employee Name', employee_user_id='employee',
                       manager_user_id='manager', manager_name='Manager Name', calibrator_user_id='hr', calibrator_name='HR Name')
    platform.add(CYCLE, dict(name='Annual review', created_by='hr', approver_id='admin', approver_name='Admin',
        participants=[participant], start_date='2026-01-01', end_date='2026-12-31'), 'draft', 'cycle')
    return service, platform, journal


def act(service, who, target, action, data=None, key=None):
    return service.execute(who, target, Action(action=action, data=data or {}, idempotency_key=key or f'{who.user_id}-{target}-{action}-key'))


def open_cycle(system):
    service, platform, _ = system
    act(service, actor('hr', 'hrms_hr_full'), 'cycle', 'submit')
    act(service, actor('admin', 'admin'), 'cycle', 'approve')
    return next(r['entity_id'] for r in platform.rows.values() if r['kind'] == REVIEW)


def goal(service, review, weight=100):
    return act(service, actor('employee'), review, 'add_goal', dict(title='Delivery', measurement='Deliver agreed milestones',
               weight=weight, target_date='2026-12-01'))['entity_id']


def test_full_lifecycle_and_employee_confidentiality(system):
    service, platform, journal = system
    review = open_cycle(system)
    goal(service, review)
    employee, manager, hr = actor('employee', 'hrms_hr_full'), actor('manager'), actor('hr', 'hrms_hr_full')
    act(service, employee, review, 'submit_goals')
    act(service, manager, review, 'approve_goals')
    act(service, hr, 'cycle', 'start_reviews')
    act(service, employee, review, 'submit_self', dict(summary='Self assessment', rating=4))
    act(service, manager, review, 'submit_manager', dict(summary='Private manager assessment', rating=3))
    own = service.dashboard(employee)['reviews'][0]
    assert 'manager_summary' not in own['data'] and 'manager_rating' not in own['data']
    assert own['feedback'] == []
    act(service, hr, 'cycle', 'start_calibration')
    act(service, hr, review, 'calibrate', dict(comment='Private calibration note', rating=4))
    assert 'calibrated_rating' not in service.dashboard(employee)['reviews'][0]['data']
    act(service, hr, 'cycle', 'publish')
    published = service.dashboard(employee)['reviews'][0]
    assert published['data']['final_rating'] == 4
    assert published['data']['manager_summary'] == 'Private manager assessment'
    assert 'calibration_comment' not in published['data']
    act(service, employee, review, 'acknowledge', dict(comment='Read and discussed'))
    act(service, hr, 'cycle', 'close')
    assert platform.rows['cycle']['state'] == 'closed'
    assert journal.audits[-1] == ('hr', 'performance:close', 'cycle')


def test_weight_return_resubmission_and_relationship_permissions(system):
    service, platform, _ = system
    review = open_cycle(system)
    goal_id = goal(service, review, 80)
    with pytest.raises(AppError, match='100%'):
        act(service, actor('employee'), review, 'submit_goals')
    with pytest.raises(AppError) as error:
        act(service, actor('unrelated', 'hrms_manager'), review, 'add_goal', {})
    assert error.value.status == 403
    act(service, actor('employee'), goal_id, 'edit_goal', dict(title='Revised goal', measurement='Delivery', weight=100, target_date='2026-12-01'))
    act(service, actor('employee'), review, 'submit_goals')
    act(service, actor('manager'), review, 'return_goals', dict(comment='Add clearer outcomes'))
    assert platform.rows[goal_id]['state'] == 'changes_requested'
    act(service, actor('employee'), review, 'submit_goals', key='resubmit-goals-key')
    act(service, actor('manager'), review, 'approve_goals')
    assert platform.rows[review]['state'] == 'self_review'


def test_cannot_self_approve_or_skip_cycle_readiness(system):
    service, platform, _ = system
    platform.rows['cycle']['data']['approver_id'] = 'hr'
    act(service, actor('hr', 'admin'), 'cycle', 'submit')
    with pytest.raises(AppError) as error:
        act(service, actor('hr', 'admin'), 'cycle', 'approve')
    assert error.value.status == 403
    platform.rows['cycle']['data']['approver_id'] = 'admin'
    act(service, actor('admin', 'admin'), 'cycle', 'approve', key='different-approval-key')
    with pytest.raises(AppError, match='approved goals'):
        act(service, actor('hr', 'hrms_hr_full'), 'cycle', 'start_reviews')


def test_partial_failure_resumes_without_duplicate_review_and_blocks_interleaving(system):
    service, platform, _ = system
    act(service, actor('hr', 'hrms_hr_full'), 'cycle', 'submit')
    platform.fail_trigger = 'approve'
    with pytest.raises(AppError, match='Injected'):
        act(service, actor('admin', 'admin'), 'cycle', 'approve')
    assert len(service.records(REVIEW)) == 1
    with pytest.raises(AppError, match='recovery'):
        act(service, actor('hr', 'hrms_hr_full'), 'cycle', 'start_reviews')
    act(service, actor('admin', 'admin'), 'cycle', 'approve')
    act(service, actor('admin', 'admin'), 'cycle', 'approve')
    assert len(service.records(REVIEW)) == 1
    assert platform.rows['cycle']['state'] == 'open'


def test_idempotency_conflict_cross_tenant_and_unrelated_read_denied(system):
    service, _, _ = system
    review = open_cycle(system)
    goal(service, review)
    assert service.dashboard(actor('stranger')) == dict(cycles=[], reviews=[], assigned_feedback=[], can_manage=False)
    with pytest.raises(AppError, match='Idempotency'):
        goal(service, review, 90)
    with pytest.raises(AppError, match='organization'):
        act(service, Actor('hr', 'other', '', frozenset({'admin'}), frozenset()), 'cycle', 'start_reviews')


def test_pending_feedback_blocks_manager_and_only_assignee_can_submit(system):
    service, platform, _ = system
    review = open_cycle(system)
    goal(service, review)
    act(service, actor('employee'), review, 'submit_goals')
    act(service, actor('manager'), review, 'approve_goals')
    act(service, actor('hr', 'hrms_hr_full'), 'cycle', 'start_reviews')
    act(service, actor('employee'), review, 'submit_self', dict(summary='Self', rating=4))
    platform.add(FEEDBACK, dict(review_id=review, project_reference='Project A', reviewer_user_id='reviewer', reviewer_name='Reviewer'), entity_id='feedback')
    with pytest.raises(AppError, match='pending'):
        act(service, actor('manager'), review, 'submit_manager', dict(summary='Manager', rating=4))
    with pytest.raises(AppError) as error:
        act(service, actor('employee'), 'feedback', 'submit_feedback', dict(rating=4, contribution='Good'))
    assert error.value.status == 403
    act(service, actor('reviewer'), 'feedback', 'submit_feedback', dict(rating=4, contribution='Good'))
    act(service, actor('manager'), review, 'submit_manager', dict(summary='Manager', rating=4))
    assert service.dashboard(actor('reviewer'))['reviews'] == []


def test_return_from_calibration_allows_manager_correction(system):
    service, platform, _ = system
    review = open_cycle(system)
    platform.rows[review]['state'] = 'calibration'
    platform.rows['cycle']['state'] = 'calibration'
    act(service, actor('hr', 'hrms_hr_full'), review, 'return_manager', dict(comment='Clarify assessment evidence'))
    assert platform.rows[review]['state'] == 'manager_review'
    act(service, actor('manager'), review, 'submit_manager', dict(summary='Corrected assessment', rating=3))
    act(service, actor('hr', 'hrms_hr_full'), review, 'calibrate', dict(comment='Evidence reviewed', rating=3))
    assert platform.rows[review]['state'] == 'publish_ready'


def test_partial_publication_keeps_ratings_private_until_cycle_published(system):
    service, platform, _ = system
    review = open_cycle(system)
    platform.rows[review]['state'] = 'published'
    platform.rows[review]['data'].update(final_rating=2, manager_rating=2, calibrated_rating=2)
    platform.rows['cycle']['state'] = 'calibration'
    row = service.dashboard(actor('employee', 'hrms_hr_full'))['reviews'][0]
    assert 'final_rating' not in row['data']
    assert 'acknowledge' not in row['actions']


def test_reassignment_snapshots_names_and_revokes_previous_manager_actions(system):
    service, platform, journal = system
    review = open_cycle(system)
    platform.rows[review]['state'] = 'manager_review'
    platform.rows['cycle']['state'] = 'review'
    manager_id, calibrator_id = '11111111-2222-3333-4444-555555555555', '11111111-2222-3333-4444-666666666666'
    service.user_options = lambda: [dict(id=manager_id, name='Replacement Manager', capabilities=[]),
        dict(id=calibrator_id, name='Replacement HR', capabilities=['performance:manage'])]
    act(service, actor('hr', 'hrms_hr_full'), review, 'reassign', dict(manager_user_id=manager_id,
        calibrator_user_id=calibrator_id, comment='Original manager is unavailable'))
    assert platform.rows[review]['data']['manager_name'] == 'Replacement Manager'
    assert service.dashboard(actor('manager'))['reviews'] == []
    assert 'submit_manager' in service.dashboard(actor(manager_id))['reviews'][0]['actions']
    op = next(op for op in journal.ops.values() if op.payload['action'] == 'reassign')
    assert op.progress['performance_plan'][0]['previous_assignment']['manager_user_id'] == 'manager'
    assert op.progress['performance_request']['data']['comment'] == 'Original manager is unavailable'

