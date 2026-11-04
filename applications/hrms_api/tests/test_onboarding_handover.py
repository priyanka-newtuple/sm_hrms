from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from hrms_app import onboarding_handover as handover, employee_work
from hrms_app.errors import AppError


class Operation:
    def __init__(self):
        self.progress = {}
        self.result = None
    def checkpoint(self, **values):
        self.progress.update(values)
    def finish(self, result):
        self.result = result


@pytest.fixture
def setup(monkeypatch):
    op = Operation()
    state = {'name': 'HR', 'moves': 0, 'assignments': [], 'fail_assignment': False}
    actor = SimpleNamespace(organization_id='org')
    @contextmanager
    def lock(org):
        assert org == 'org'
        yield object()
    journal = SimpleNamespace(lock=lock, operation=lambda *args: op)
    monkeypatch.setattr(handover.routing, 'context', lambda *args: ({}, {}, state['name']))
    monkeypatch.setattr(handover.routing, 'assignees', lambda *args: {
        'can_assign': True, 'state': 'IT', 'items': [{'id': 'office'}]})
    def move(*args, **kwargs):
        state['moves'] += 1
        state['name'] = 'IT'
        return {'current_state': 'IT'}
    def assign(*args):
        if state['fail_assignment']:
            raise AppError(422, 'Assignment rejected')
        state['assignments'].append(args[-1])
    monkeypatch.setattr(employee_work, 'transition_employee', move)
    monkeypatch.setattr(handover.routing, 'assign', assign)
    def run(next_user='office'):
        return handover.transition_with_handover(object(), actor, 'e', 'w', 'approve', 'request-key', journal, next_user)
    return run, state, op


def test_validated_handover_assigns_next_actor_and_replays_once(setup):
    run, state, op = setup
    assert run() == {'current_state': 'IT'}
    assert run() == op.result
    assert state['moves'] == 1
    assert state['assignments'] == ['office']


def test_missing_or_ineligible_next_actor_never_moves(setup):
    run, state, _ = setup
    for user in [None, 'hr', 'outsider']:
        with pytest.raises(AppError, match='eligible'):
            run(user)
    assert state['moves'] == 0


def test_assignment_failure_resumes_without_repeating_transition(setup):
    run, state, _ = setup
    state['fail_assignment'] = True
    with pytest.raises(AppError, match='stage moved'):
        run()
    state['fail_assignment'] = False
    run()
    assert state['moves'] == 1
    assert state['assignments'] == ['office']


def test_changed_state_does_not_assign_wrong_stage(setup):
    run, state, _ = setup
    state['fail_assignment'] = True
    with pytest.raises(AppError):
        run()
    state['name'] = 'Completed'
    with pytest.raises(AppError, match='moved again'):
        run()
    assert not state['assignments']


def test_replay_checks_current_visibility(setup, monkeypatch):
    run, _, _ = setup
    run()
    def denied(*args):
        raise AppError(404, 'Unavailable')
    monkeypatch.setattr(handover.routing, 'context', denied)
    with pytest.raises(AppError, match='Unavailable'):
        run()


def test_terminal_transition_does_not_need_next_assignee(setup, monkeypatch):
    run, state, _ = setup
    monkeypatch.setattr(handover.routing, 'assignees', lambda *args: {
        'can_assign': True, 'state': 'IT', 'terminal': True, 'items': []})
    run(None)
    assert state['moves'] == 1
    assert not state['assignments']
