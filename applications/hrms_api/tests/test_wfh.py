from datetime import date
from dataclasses import replace
from types import SimpleNamespace

import pytest

from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.service import HrmsService
from hrms_app.wfh import WfhService, PolicyInput, RequestInput, DecisionInput
from hrms_app.wfh_catalog import POLICY, REQUEST
from test_performance import Platform, Journal, actor


class WfhJournal(Journal):
    def execute(self, sql, params):
        return SimpleNamespace(fetchone=lambda: next(((k,) for k, o in self.ops.items()
            if k != params[1] and not o.result and 'wfh_plan' in o.progress), None))


@pytest.fixture
def system(monkeypatch):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 6)
    monkeypatch.setattr('hrms_app.wfh.date', Today)
    p, j = Platform(), WfhJournal()
    for user in ('employee', 'other', 'hr'):
        p.add('HRMS.Employee', {'platform_user_id': user, 'first_name': user, 'last_name': 'Person', 'employment_status': 'active'}, entity_id=user)
    s = WfhService(HrmsService(p, j, 'example.com'))
    monkeypatch.setattr(s, 'holiday_dates', lambda: {'2026-10-14'})
    def labels(platform, rows):
        definition = pack_by_type(REQUEST).workflow_definition()
        return [{**r, 'current_state': r['state'], 'state_label': r['state'].title(),
                 'workflow_configuration': {'transitions': [{'trigger': t['trigger'], 'from_state': t['from'], 'label': t['label']} for t in definition['transitions']]}} for r in rows]
    monkeypatch.setattr('hrms_app.wfh.configured_workflow_rows', labels)
    monkeypatch.setattr('hrms_app.form_config.form_configuration', lambda platform, who, kind: {'fields': pack_by_type(kind).fields})
    return s, p, j


def policy(s, days=10, revision=0, key='policy-key-0001'):
    return s.save_policy(actor('hr', 'hrms_hr_full'), PolicyInput(year=2026, annual_days=days, notice_days=0, revision=revision, idempotency_key=key))


def create(s, user='employee', days=None, key='request-key-0001'):
    return s.create(actor(user, 'hrms_employee'), RequestInput(dates=days or ['2026-10-12'], reason='Private reason', idempotency_key=key))


def decide(s, entity, trigger, user='hr', role='hrms_hr_full', key=None):
    return s.decide(actor(user, role), entity, DecisionInput(trigger=trigger, idempotency_key=key or f'{trigger}-key-0001'))


def test_policy_request_approval_privacy_and_cancellation(system):
    s, p, j = system
    policy(s)
    result = create(s)
    own = s.board(actor('employee', 'hrms_employee'), 2026)
    assert own['balance'] == {'used': 0, 'upcoming': 0, 'pending': 1, 'remaining': 9}
    assert s.board(actor('other', 'hrms_employee'), 2026)['requests'] == []
    assert own['calendar'] == []
    decide(s, result['entity_id'], 'approve')
    public = s.board(actor('other', 'hrms_employee'), 2026)
    assert public['calendar'][0]['dates'] == ['2026-10-12']
    assert 'reason' not in public['calendar'][0]
    assert 'policy_id' not in public['calendar'][0]
    decide(s, result['entity_id'], 'cancel', 'employee', 'hrms_employee')
    assert s.board(actor('employee', 'hrms_employee'), 2026)['balance']['remaining'] == 10
    assert j.audits


def test_allowance_duplicates_and_policy_reduction(system):
    s, _, _ = system
    policy(s, 1)
    create(s)
    for days in (['2026-10-12'], ['2026-10-13']):
        with pytest.raises(AppError):
            create(s, days=days, key='second-request-key')
    with pytest.raises(AppError, match='lower'):
        policy(s, 0, 1, 'policy-key-0002')
    with pytest.raises(AppError, match='changed'):
        policy(s, 10, 0, 'policy-key-0003')


@pytest.mark.parametrize('days', [['2026-10-04'], ['2026-10-10'], ['2026-10-14'], ['2026-10-12', '2027-01-04']])
def test_dates_holidays_and_year_boundaries(system, days):
    s, _, _ = system
    policy(s)
    with pytest.raises(AppError):
        create(s, days=days)


def test_hr_authorization_no_self_approval_and_cross_tenant(system):
    s, _, _ = system
    policy(s)
    entity = create(s, 'hr')['entity_id']
    with pytest.raises(AppError, match='Another HR'):
        decide(s, entity, 'approve')
    with pytest.raises(AppError):
        decide(s, entity, 'approve', 'other', 'hrms_manager')
    with pytest.raises(AppError):
        s.board(replace(actor('hr', 'hrms_hr_full'), organization_id='another-org'), 2026)
    with pytest.raises(AppError):
        s.save_policy(actor('employee', 'hrms_employee'), PolicyInput(year=2026, annual_days=10, notice_days=0, revision=1, idempotency_key='policy-hack-key'))


def test_missing_policy_and_employee_profile(system):
    s, _, _ = system
    with pytest.raises(AppError, match='policy'):
        create(s)
    policy(s)
    with pytest.raises(AppError, match='employee profile'):
        create(s, 'unknown')


def test_replay_and_uncertain_transition_blocks_other_mutations(system):
    s, p, _ = system
    policy(s)
    first = create(s)
    assert create(s) == first
    assert len(s.rows(REQUEST)) == 1
    p.fail_trigger = 'approve'
    with pytest.raises(AppError):
        decide(s, first['entity_id'], 'approve')
    with pytest.raises(AppError, match='incomplete'):
        create(s, 'other', key='another-request-key')
    decide(s, first['entity_id'], 'approve')
    decide(s, first['entity_id'], 'approve')
    assert p.rows[first['entity_id']]['state'] == 'approved'


def test_leave_conflicts_both_directions(system):
    s, p, j = system
    policy(s)
    p.add('HRMS.LeaveRequest', {'employee_id': 'employee', 'start_date': '2026-10-12', 'end_date': '2026-10-12'}, 'approved')
    with pytest.raises(AppError, match='leave request'):
        create(s)
    create(s, days=['2026-10-13'], key='clear-date-key')
    with pytest.raises(AppError, match='overlapping WFH'):
        s.check_leave_conflict(j, actor('employee'), 'employee', date(2026, 10, 13), date(2026, 10, 13))


def test_lost_create_response_recovers_same_native_record(system, monkeypatch):
    s, p, _ = system
    policy(s)
    original = p.create_record
    def lost_response(*args):
        original(*args)
        raise AppError(503, 'Connection lost after write')
    monkeypatch.setattr(p, 'create_record', lost_response)
    with pytest.raises(AppError):
        create(s)
    monkeypatch.setattr(p, 'create_record', original)
    result = create(s)
    assert len(s.rows(REQUEST)) == 1
    decide(s, result['entity_id'], 'reject')
    assert s.board(actor('employee', 'hrms_employee'), 2026)['balance']['remaining'] == 10


def test_inbox_includes_next_year_requests(system):
    s, _, _ = system
    s.save_policy(actor('hr', 'hrms_hr_full'), PolicyInput(year=2027, annual_days=12, notice_days=0, revision=0, idempotency_key='next-year-policy'))
    create(s, days=['2027-01-04'])
    assert s.inbox(actor('hr', 'hrms_hr_full'))[0]['dates'] == ['2027-01-04']


def test_configured_form_constraints_enforced_by_server(system, monkeypatch):
    s, _, _ = system
    policy(s)
    monkeypatch.setattr('hrms_app.form_config.form_configuration', lambda *args: {'fields': [{'field': 'reason', 'read_only': True}]})
    with pytest.raises(AppError, match='read-only'):
        create(s)


def test_approval_rechecks_leave_conflicts(system):
    s, p, _ = system
    policy(s)
    entity = create(s)['entity_id']
    p.add('HRMS.LeaveRequest', {'employee_id': 'employee', 'start_date': '2026-10-12', 'end_date': '2026-10-12'}, 'approved')
    with pytest.raises(AppError, match='leave request'):
        decide(s, entity, 'approve')
