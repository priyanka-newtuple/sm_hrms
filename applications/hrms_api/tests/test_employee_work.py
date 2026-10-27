from types import SimpleNamespace

import pytest
from hrms_app.employee_work import employee_work, transition_employee
from hrms_app.errors import AppError


def setup(allowed=True, org="org"):
    calls = []
    actor = SimpleNamespace(
        token="human-token", organization_id="org", user_id="user", roles={"superadmin"}
    )

    def request(method, path, **kw):
        assert kw["token"] == "human-token"
        calls.append((method, path, kw))
        if method == "POST":
            return {"current_state": "Email Setup"}
        if path.startswith("/workflow-state-machines/"):
            return {
                "machine_name": "employee",
                "definition": {"transitions": [{"key": "next", "trigger": "next"}]},
            }
        return {
            "has_more": False,
            "items": [
                {
                    "entity_id": "employee",
                    "entity_type": "HRMS.Employee",
                    "organization_id": org,
                    "workflow_id": "workflow",
                    "machine_display_name": "Add Employee",
                    "display_name": "EMP-1",
                    "summary_fields": {"first_name": "Manoj", "last_name": "Gupta"},
                    "current_state": "Employee Registration",
                    "transition_options": [
                        {
                            "trigger": "next",
                            "label": "Move to Email Setup",
                            "to_state": "Email Setup",
                            "allowed": allowed,
                        }
                    ],
                }
            ],
        }

    return SimpleNamespace(request=request), actor, calls


def test_native_names_states_and_actions_use_human_permissions():
    p, a, calls = setup()
    item = employee_work(p, a)[0]
    assert (
        item["title"] == "Manoj Gupta"
        and item["current_state"] == "Employee Registration"
    )
    assert (
        transition_employee(p, a, "employee", "workflow", "next", "key-1234")[
            "current_state"
        ]
        == "Email Setup"
    )
    assert calls[-1][2]["json"]["workflow_id"] == "workflow"


def test_unfilled_required_fields_do_not_hide_the_task():
    p, a, _calls = setup(False)
    assert employee_work(p, a)[0]["actions"][0]["trigger"] == "next"


def test_foreign_tenant_result_is_rejected():
    p, a, _ = setup(org="other")
    with pytest.raises(AppError):
        employee_work(p, a)


def test_inbox_fetches_each_workflow_once_per_request():
    from copy import deepcopy

    p, a, calls = setup()
    original = p.request

    def request(method, path, **kwargs):
        response = original(method, path, **kwargs)
        if path == '/workflow-enrollments':
            second = deepcopy(response['items'][0])
            second['entity_id'] = 'second-employee'
            response['items'].append(second)
        return response

    p.request = request
    assert len(employee_work(p, a)) == 2
    assert sum(path == '/workflow-state-machines/workflow' for _, path, _ in calls) == 1
    employee_work(p, a)
    assert sum(path == '/workflow-state-machines/workflow' for _, path, _ in calls) == 2


def test_form_reads_independent_data_concurrently_with_human_access():
    from threading import Barrier
    from hrms_app.employee_work import employee_form

    p, a, _ = setup()
    original = p.request
    barrier = Barrier(3)
    responses = {
        '/entity-records/employee': {'organization_id': 'org', 'data': {}},
        '/workflow-state-machines/workflow': {'definition': {}},
        '/roles/my-permissions': {'field_permissions': []},
    }

    def request(method, path, **kwargs):
        assert kwargs['token'] == a.token
        if path in responses:
            barrier.wait(timeout=5)
            return responses[path]
        return original(method, path, **kwargs)

    p.request = request
    assert employee_form(p, a, 'employee', 'workflow')['values'] == {}
    responses['/entity-records/employee']['organization_id'] = 'other'
    with pytest.raises(AppError, match='another organization'):
        employee_form(p, a, 'employee', 'workflow')


def test_wrong_workflow_or_trigger_cannot_be_executed():
    p, a, calls = setup()
    with pytest.raises(AppError):
        transition_employee(p, a, "employee", "other", "next", "key-1234")
    with pytest.raises(AppError):
        transition_employee(p, a, "employee", "workflow", "bypass", "key-1234")
    assert all(c[0] == "GET" for c in calls)


def test_onboarding_employee_cannot_see_another_employee_task():
    p, a, _calls = setup()
    a.roles = {"hrms_onboarding_employee"}
    p.call = lambda method, path: []
    assert employee_work(p, a) == []


def test_state_form_prefills_previous_fields_and_rejects_edits_to_them():
    from hrms_app.employee_work import employee_form, save_employee_form

    p, a, _calls = setup()
    old_request = p.request

    def request(method, path, **kw):
        if path == "/roles/my-permissions":
            return {"field_permissions": []}
        if path == "/entity-records/employee":
            return {
                "organization_id": "org",
                "data": {"first_name": "Earlier", "work_email": "new@example.com"},
            }
        if path.startswith("/workflow-state-machines/"):
            return {
                "definition": {
                    "entity_schema": {
                        "fields": [{"field": "first_name", "type": "string"}]
                    },
                    "method_schemas": [
                        {"state_name": "Earlier step", "method_name": "Earlier", "fields": [{"field": "first_name", "type": "string"}]},
                        {
                            "state_name": "Employee Registration",
                            "method_name": "Configured",
                            "fields": [{"field": "work_email", "type": "email"}],
                        }
                    ],
                }
            }
        return old_request(method, path, **kw)

    p.request = request
    form = employee_form(p, a, "employee", "workflow")
    assert form["values"]["first_name"] == "Earlier"
    assert form["previous_fields"][0]["read_only"]
    assert [f["field"] for f in form["fields"]] == ["work_email"]
    with pytest.raises(AppError):
        save_employee_form(p, a, "employee", "workflow", {"first_name": "Changed"})

def test_profile_task_belongs_to_employee_not_superadmin(monkeypatch):
    monkeypatch.setenv('HRMS_EMPLOYEE_PROFILE_FORM_ID', 'profile-form')
    p, a, _ = setup()
    original = p.request
    def request(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path.startswith('/workflow-state-machines/'):
            result['definition']['states'] = [{'name': 'Employee Registration', 'method_refs': [{'method_id': 'profile-form'}]}]
        elif path == '/workflow-enrollments':
            result['items'][0]['summary_fields']['platform_user_id'] = 'employee-user'
        return result
    p.request = request
    assert employee_work(p, a) == []
    with pytest.raises(AppError):
        transition_employee(p, a, 'employee', 'workflow', 'next', 'no-proxy')
    a.user_id = 'employee-user'
    assert employee_work(p, a)[0]['actions']


def test_own_status_remains_when_no_action_is_available():
    p, a, _ = setup()
    original = p.request
    def request(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path == '/workflow-enrollments':
            result['items'][0]['summary_fields']['platform_user_id'] = a.user_id
            result['items'][0]['transition_options'] = []
        return result
    p.request = request
    item = employee_work(p, a)[0]
    assert item['is_own_onboarding']
    assert item['actions'] == []

def test_feedback_projects_only_values_returned_by_native_permissions(monkeypatch):
    monkeypatch.setenv("HRMS_EMPLOYEE_PROFILE_FORM_ID", "profile-form")
    p, a, _ = setup()
    original = p.request
    def request(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path == '/workflow-enrollments':
            assert 'hr_verification_notes' in kwargs['params']['fields']
            result['items'][0]['summary_fields']['hr_verification_notes'] = 'Correct the access details.'
            result['items'][0]['summary_fields']['platform_user_id'] = a.user_id
        elif path.startswith('/workflow-state-machines/'):
            result['definition']['states'] = [{'name': 'Employee Registration', 'method_refs': [{'method_id': 'profile-form'}]}]
        return result
    p.request = request
    assert employee_work(p, a)[0]['verifier_feedback'] == 'Correct the access details.'
    p.request = original
    assert employee_work(p, a)[0]['verifier_feedback'] is None


@pytest.mark.parametrize('reason', [None, '', '   '])
def test_configured_required_reason_blocks_empty_return(monkeypatch, reason):
    import hrms_app.employee_work as module
    p, a, calls = setup()
    original = p.request
    def request(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path.startswith('/workflow-state-machines/'):
            result['definition']['transitions'][0]['required_fields'] = [{'field':'hr_verification_notes','type':'text','required':True}]
        return result
    p.request = request
    monkeypatch.setattr(module, 'employee_form', lambda *args: {'values': {'hr_verification_notes': reason}})
    with pytest.raises(AppError, match='correction reason'):
        transition_employee(p, a, 'employee', 'workflow', 'next', 'empty-reason')
    assert all(method != 'POST' for method, *_ in calls)


def test_configured_return_preserves_native_transition_execution(monkeypatch):
    import hrms_app.employee_work as module
    p, a, calls = setup()
    original = p.request
    def request(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path.startswith('/workflow-state-machines/'):
            result['definition']['transitions'][0]['required_fields'] = [{'field':'hr_verification_notes','type':'text','required':True}]
        return result
    p.request = request
    monkeypatch.setattr(module, 'employee_form', lambda *args: {'values': {'hr_verification_notes': 'Please correct the address.'}})
    transition_employee(p, a, 'employee', 'workflow', 'next', 'with-reason')
    assert calls[-1][0] == 'POST'
    assert calls[-1][2]['token'] == a.token

def test_submitted_feedback_does_not_appear_as_outstanding():
    p, a, _ = setup()
    original = p.request
    def request(method, path, **kwargs):
        result = original(method, path, **kwargs)
        if path == '/workflow-enrollments':
            result['items'][0]['summary_fields']['hr_verification_notes'] = 'Previously requested correction'
            result['items'][0]['current_state'] = 'Onboarding Verification'
        return result
    p.request = request
    assert employee_work(p, a)[0]['verifier_feedback'] is None


def test_provisioning_feedback_retained_in_history_not_active_form(monkeypatch):
    import hrms_app.employee_work as module
    p, a, _ = setup()
    a.roles = {'hrms_office_admin'}
    monkeypatch.setattr(module, 'employee_enrollments', lambda *_: [{'entity_id':'employee','workflow_id':'workflow','current_state':'IT'}])
    note={'field':'hr_verification_notes','type':'text'}
    def request(method,path,**kwargs):
        if path=='/entity-records/employee':
            return {'organization_id':'org','data':{'hr_verification_notes':'Earlier correction'}}
        if path=='/roles/my-permissions':
            return {'field_permissions':[{'entity_type':'HRMS.Employee','field_name':'hr_verification_notes','can_view':True,'can_edit':False}]}
        return {'definition':{'method_schemas':[{'state_name':'IT','method_name':'IT','fields':[note]}]}}
    p.request=request
    result=module.employee_form(p,a,'employee','workflow')
    assert result['verifier_feedback'] is None
    assert result['fields']==[]
    assert result['previous_fields'][0]['field']=='hr_verification_notes'
    assert result['values']['hr_verification_notes']=='Earlier correction'


def test_final_signoff_only_appears_for_initiating_hr_even_for_other_superadmin(monkeypatch):
    monkeypatch.setenv("HRMS_EMPLOYEE_SIGNOFF_FORM_ID", "signoff-form")
    p, actor, calls = setup()
    original = p.request
    def request(method,path,**kw):
        if path.startswith('/entity-records/'):
            return {'organization_id':'org','owner_id':'user'}
        result=original(method,path,**kw)
        if path.startswith('/workflow-state-machines/'):
            result['definition']['states']=[{'name':'Employee Registration','method_refs':[{'method_id':'signoff-form'}]}]
        return result
    p.request=request
    assert len(employee_work(p,actor)) == 1
    actor.user_id='another-admin'
    assert employee_work(p,actor) == []
    with pytest.raises(AppError):
        transition_employee(p,actor,'employee','workflow','next','retry-id')
    assert not any(method=='POST' for method,_,_ in calls)


def test_tracker_keeps_other_owners_and_terminal_enrollments_without_adding_actions(monkeypatch):
    import hrms_app.employee_work as module
    p,actor,_=setup()
    actor.permissions={'tenant.org.hrms.onboarding:view'}
    rows=[{'entity_id':'employee','workflow_id':'workflow','current_state':state,
           'summary_fields':{'first_name':'Test'},'display_name':'EMP','machine_display_name':'Configured'}
          for state in ['Review','Done']]
    monkeypatch.setattr(module,'employee_enrollments',lambda *_:rows)
    monkeypatch.setattr(module,'employee_work',lambda *_:[])
    p.users=lambda:[{'id':'hr','organization_id':'org','full_name':'HR owner','email':'hr@example.com'}]
    def request(method,path,**kw):
        assert method=='GET' and kw['token']=='human-token'
        if path.startswith('/entity-records/'):
            return {'organization_id':'org','owner_id':'hr','assignee_id':None}
        return {'machine_name':'configured_employee','version':2,
                'definition':{'states':[{'name':'Review','tags':[]},{'name':'Done','tags':['terminal']}]}}
    p.request=request
    result=module.onboarding_tracker(p,actor)
    assert [r['completed'] for r in result]==[False,True]
    assert all(r['actions']==[] and r['started_by']=='HR owner' for r in result)
    actor.permissions=set()
    with pytest.raises(AppError): module.onboarding_tracker(p,actor)


def feedback_workflow():
    return {'definition': {'states': [
        {'name':'Profile','method_refs':[{'method_id':'profile-form'}]},
        {'name':'Review'}, {'name':'IT'}, {'name':'Signoff'}, {'name':'Done'}],
        'transitions': [
            {'from':'Profile','to_state':'Review'},
            {'from':'Review','to_state':'Profile','required_fields':[
                {'field':'hr_verification_notes','required':True}]},
            {'from':'Review','to_state':'IT','required_fields':[{'field':'hr_verification_notes','required':True}]},
            {'from':'IT','to_state':'Signoff'},
            {'from':'Signoff','to_state':'Done'}]}}


@pytest.mark.parametrize('state,expected', [('Profile','requested'),('Review','submitted'),
    ('IT','resolved'),('Signoff','resolved'),('Done','resolved'),('Registration',None)])
def test_feedback_status_follows_native_graph(monkeypatch,state,expected):
    from hrms_app.employee_work import feedback_stage
    monkeypatch.setenv('HRMS_EMPLOYEE_PROFILE_FORM_ID','profile-form')
    assert feedback_stage(feedback_workflow(),state)==expected


@pytest.mark.parametrize('state', ['IT','Signoff','Done'])
def test_resolved_notes_are_history_even_for_superadmin(monkeypatch,state):
    import hrms_app.employee_work as module
    monkeypatch.setenv('HRMS_EMPLOYEE_PROFILE_FORM_ID','profile-form')
    p,a,calls=setup()
    monkeypatch.setattr(module,'employee_enrollments',lambda *_:[
        {'entity_id':'employee','workflow_id':'workflow','current_state':state}])
    note={'field':'hr_verification_notes','type':'text'}
    w=feedback_workflow()
    w['definition']['method_schemas']=[{'state_name':state,'method_name':state,'fields':[note]}]
    def request(method,path,**kw):
        calls.append((method,path,kw))
        if path=='/entity-records/employee':
            return {'organization_id':'org','data':{'hr_verification_notes':'Incorrect IFSC code'}}
        if path=='/roles/my-permissions':return {'field_permissions':[]}
        return w
    p.request=request
    result=module.employee_form(p,a,'employee','workflow')
    assert result['feedback_status']=='resolved'
    assert result['previous_feedback']=='Incorrect IFSC code'
    assert result['verifier_feedback'] is None
    assert not result['fields'] and not result['previous_fields']
    with pytest.raises(AppError,match='Only editable fields'):
        module.save_employee_form(p,a,'employee','workflow',{'hr_verification_notes':'overwrite'})
    assert all(method=='GET' for method,_,_ in calls)


def test_unknown_configuration_does_not_claim_resolution(monkeypatch):
    from hrms_app.employee_work import feedback_stage
    monkeypatch.delenv('HRMS_EMPLOYEE_PROFILE_FORM_ID',raising=False)
    assert feedback_stage(feedback_workflow(),'Done') is None
