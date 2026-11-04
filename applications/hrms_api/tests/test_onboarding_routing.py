from types import SimpleNamespace
import pytest
from hrms_app import onboarding_routing as routing
from hrms_app.errors import AppError


def system(monkeypatch):
    monkeypatch.setenv('HRMS_EMPLOYEE_PAYROLL_FORM_ID','payroll')
    monkeypatch.setenv('HRMS_EMPLOYEE_CANCELLED_FORM_ID','cancelled')
    workflow={'machine_name':'onboard','definition':{'states':[{'name':'HR','tags':[]},{'name':'Payroll','method_refs':[{'method_id':'payroll'}]},{'name':'Cancelled','tags':['terminal'],'method_refs':[{'method_id':'cancelled'}]}], 'transitions':[{'key':'continue','from':'HR','to_state':'Payroll'},{'key':'cancel','from':'HR','to_state':'Cancelled'}]}}
    actor=SimpleNamespace(organization_id='org',roles={'hrms_hr_full'},token='human')
    record={'organization_id':'org','data':{},'assignee_id':None}
    monkeypatch.setattr(routing,'context',lambda *args:(record,workflow,'HR'))
    users=[{'id':k,'organization_id':'org','status':'active','email':k+'@example.com'} for k in ('hr','office','cancel-only','super')]
    users.append({'id':'outsider','organization_id':'other','status':'active','email':'other@example.com'})
    roles={'hr':{'name':'hrms_hr_full','transition_permissions':[{'machine_name':'onboard','transition_key':'continue'}]},'office':{'name':'hrms_office_admin','transition_permissions':[]},'cancel-only':{'name':'hrms_hr_full','transition_permissions':[{'machine_name':'onboard','transition_key':'cancel'}]},'super':{'name':'superadmin','transition_permissions':[]}}
    def call(method,path):
        if path.startswith('/roles/users/'):
            key=path.split('/')[3]
            return [{'role_id':key,'organization_id':'org'}]
        return {**roles[path.split('/')[-1]],'organization_id':'org','workflow_permissions':[{'machine_name':'onboard'}]}
    platform=SimpleNamespace(email='service@example.com',users=lambda:users,call=call,request=lambda method,path,**k: {'entity_permissions':[{'entity_type':'HRMS.Employee','action':'edit','allowed':True}]} if method=='GET' and path=='/roles/my-permissions' else pytest.fail('invalid assignment must not write'))
    return platform,actor


def test_candidates_exclude_cancellation_only_and_other_tenants(monkeypatch):
    p,a=system(monkeypatch)
    assert [x['id'] for x in routing.assignees(p,a,'e','w')['items']]==['hr']


def test_assignment_revalidates_candidates(monkeypatch):
    p,a=system(monkeypatch)
    with pytest.raises(AppError,match='authorized'): routing.assign(p,a,'e','w','office')


def test_employee_cannot_manage_assignments(monkeypatch):
    p,a=system(monkeypatch); a.roles={'hrms_employee'}
    p.request=lambda *args,**kwargs: {'entity_permissions':[]}
    assert routing.assignees(p,a,'e','w')['can_assign'] is False


def test_transition_grant_without_workflow_access_is_not_eligible(monkeypatch):
    p,a=system(monkeypatch)
    original=p.call
    def call(method,path):
        result=original(method,path)
        if path=='/roles/hr': result['workflow_permissions']=[]
        return result
    p.call=call
    assert routing.assignees(p,a,'e','w')['items']==[]


def test_foreign_role_membership_fails_closed(monkeypatch):
    p,a=system(monkeypatch)
    original=p.call
    p.call=lambda method,path: ([{'role_id':'foreign','organization_id':'other'}]
        if path=='/roles/users/hr/roles' else original(method,path))
    with pytest.raises(AppError,match='organization'):
        routing.assignees(p,a,'e','w')


def test_inactive_user_is_not_an_eligible_assignee(monkeypatch):
    p,a=system(monkeypatch)
    users=p.users()
    next(u for u in users if u['id']=='hr')['status']='suspended'
    p.users=lambda:users
    assert routing.assignees(p,a,'e','w')['items']==[]


def test_fixed_assignment_cannot_offer_another_user(monkeypatch):
    from hrms_app import employee_work
    p,a=system(monkeypatch)
    monkeypatch.setattr(employee_work,'is_employee_profile_step',lambda *args:True)
    monkeypatch.setattr(routing,'fixed_user',lambda *args:'office')
    options=routing.assignees(p,a,'e','w')
    assert options['fixed'] is True
    # The fixed user still needs the native grants; never substitute another user.
    assert options['items']==[]
