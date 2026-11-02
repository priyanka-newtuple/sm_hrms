from datetime import datetime, UTC
from types import SimpleNamespace
import pytest
from hrms_app.errors import AppError
from hrms_app.offboarding_simple import departure_due, role_grants
from hrms_app.offboarding_participation import EmployeeOffboarding
from hrms_app.platform import Actor


def test_departure_uses_local_last_working_day(monkeypatch):
    monkeypatch.setenv('HRMS_TIMEZONE', 'Asia/Kolkata')
    departure_due({'confirmed_last_day': '2026-10-30'}, datetime(2026,10,29,19,tzinfo=UTC))
    with pytest.raises(AppError, match='on or after'):
        departure_due({'confirmed_last_day': '2026-10-30'}, datetime(2026,10,29,18,tzinfo=UTC))
    with pytest.raises(AppError, match='valid last working day'):
        departure_due({}, datetime.now(UTC))


def test_native_role_scope_is_checked():
    actor = Actor('user','org','token',frozenset(),frozenset())
    platform = SimpleNamespace(call=lambda *a: [{'organization_id':'other','role_id':'role'}])
    with pytest.raises(AppError,match='scope'):
        role_grants(platform,actor)


@pytest.mark.parametrize('assigned,grant,expected', [(True,True,True),(False,True,False),(True,False,False)])
def test_clearance_needs_assignment_and_native_transition(monkeypatch,assigned,grant,expected):
    actor = Actor('pm','org','token',frozenset(),frozenset())
    record = {'entity_id':'exit','assignee_id':'pm' if assigned else 'other','data':{'employee_id':'employee','exit_employee_name':'Name','project_release_approved':'Yes','exit_employee_feedback':'PRIVATE'}}
    state = {'name':'Project Manager Clearance','on_state_actions':[{'kind':'entity.assign_user','config':{'user_id':'$entity.offboarding_project_manager_id'}}]}
    workflow = {'machine_name':'exit','definition':{'transitions':[{'key':'approve','trigger':'approve_project_release','from':state['name']} ]}}
    monkeypatch.setattr('hrms_app.offboarding_participation.role_grants', lambda *a: ({'project_release_approved':(True,True)}, {('exit','approve')} if grant else set(), {'exit'}))
    service = SimpleNamespace(platform=None,service=None,fields=lambda *a:[{'field':'project_release_approved'},{'field':'exit_employee_feedback'}])
    result = EmployeeOffboarding(service).simple_detail(actor,record,workflow,state,False)
    assert result['editable'] == expected
    assert 'exit_employee_feedback' not in result['values']
    assert all(f['field'] != 'exit_employee_feedback' for f in result['fields'])
