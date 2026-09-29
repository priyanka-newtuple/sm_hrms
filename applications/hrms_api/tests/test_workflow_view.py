from types import SimpleNamespace

import pytest

from hrms_app.errors import AppError
from hrms_app.workflow_view import workflow_rows


def employee(entity_id, user_id, code, manager=None):
    return dict(entity_id=entity_id, data=dict(platform_user_id=user_id, employee_code=code,
                reports_to_employee_code=manager, first_name=entity_id.title(), last_name='Employee'))


class Service:
    def __init__(self, employees):
        self.people = employees
        self.platform = self

    def employees(self):
        return self.people

    def onboarding(self, actor):
        # Real service owns authorization; projection must not broaden its result.
        return [dict(entity_id='allowed-case', identifier='ONB-1', employee_name='Allowed Employee',
                     state='in_progress', completed_steps=0, total_steps=8, can_complete_case=False,
                     steps=[dict(readiness='ready', owner_name='Office Admin', title='Create account', due_date=None)])]

    def states(self, machine):
        return {'own-leave': 'pending', 'report-leave': 'approved', 'unrelated-leave': 'pending'}

    def records(self, kind, fields):
        return [dict(entity_id=key+'-leave', data=dict(employee_id=key, identifier='LVE-'+key,
                     start_date='2026-10-01', end_date='2026-10-02', leave_type='annual', reason='Private reason'))
                for key in ['own', 'report', 'unrelated']]


def test_workflow_projection_includes_only_authorized_cases_own_and_direct_report_leave():
    service = Service([employee('own', 'actor', 'M1'), employee('report', 'report-user', 'E1', 'M1'),
                       employee('unrelated', 'other-user', 'E2', 'M2')])
    rows = workflow_rows(service, SimpleNamespace(user_id='actor'))
    assert {r['entity_id'] for r in rows} == {'allowed-case', 'own-leave', 'report-leave'}
    by_id = {r['entity_id']: r for r in rows}
    assert by_id['own-leave']['leave_view'] == 'mine'
    assert by_id['report-leave']['leave_view'] == 'approvals'
    assert by_id['allowed-case']['title'] == 'Allowed Employee'
    assert by_id['allowed-case']['next_action'] == 'Create account'


def test_bootstrap_admin_has_no_implicit_access_to_all_leave_records():
    rows = workflow_rows(Service([employee('unrelated', 'other-user', 'E2')]), SimpleNamespace(user_id='admin'))
    assert [r['entity_id'] for r in rows] == ['allowed-case']


def test_missing_manager_codes_do_not_match_unrelated_leave():
    rows = workflow_rows(Service([employee('own', 'actor', None), employee('unrelated', 'other', 'E2')]),
                         SimpleNamespace(user_id='actor'))
    assert {r['entity_id'] for r in rows} == {'allowed-case', 'own-leave'}


def test_duplicate_identity_links_fail_closed():
    with pytest.raises(AppError) as error:
        workflow_rows(Service([employee('one', 'actor', 'E1'), employee('two', 'actor', 'E2')]),
                      SimpleNamespace(user_id='actor'))
    assert error.value.status == 409
