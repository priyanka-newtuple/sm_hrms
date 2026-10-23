from types import SimpleNamespace

from hrms_app.workflow_view import employee_workflow_rows


def test_directory_includes_completed_native_onboarding_without_personal_profile(monkeypatch):
    actor = SimpleNamespace(organization_id='org', roles={'superadmin'},
                            permissions={'tenant.org.hrms.onboarding:view'})
    items = [dict(entity_id='employee', workflow_id='native-version', title='Employee',
                  identifier='EMP-1', current_state='Custom completed state', completed=True,
                  workflow_label='Configured workflow', actions=[], due_date=None)]
    monkeypatch.setattr('hrms_app.employee_work.onboarding_tracker', lambda p, a: items)
    rows = employee_workflow_rows(object(), actor)
    assert len(rows) == 1
    assert rows[0]['is_terminal'] is True
    assert rows[0]['state_label'] == 'Custom completed state'
    assert rows[0]['employee_work']['workflow_id'] == 'native-version'


def test_directory_does_not_fetch_employee_work_without_permission(monkeypatch):
    actor = SimpleNamespace(organization_id='org', roles=set(), permissions=set())
    def forbidden(*args):
        raise AssertionError('Should not query onboarding')
    monkeypatch.setattr('hrms_app.employee_work.onboarding_tracker', forbidden)
    assert employee_workflow_rows(object(), actor) == []
