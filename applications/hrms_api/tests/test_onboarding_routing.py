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
        return {**roles[path.split('/')[-1]],'organization_id':'org'}
    platform=SimpleNamespace(email='service@example.com',users=lambda:users,call=call,request=lambda *a,**k:pytest.fail('invalid assignment must not write'))
    return platform,actor


def test_candidates_exclude_cancellation_only_and_other_tenants(monkeypatch):
    p,a=system(monkeypatch)
    assert [x['id'] for x in routing.assignees(p,a,'e','w')['items']]==['hr']


def test_assignment_revalidates_candidates(monkeypatch):
    p,a=system(monkeypatch)
    with pytest.raises(AppError,match='authorized'): routing.assign(p,a,'e','w','office')


def test_employee_cannot_manage_assignments(monkeypatch):
    p,a=system(monkeypatch); a.roles={'hrms_employee'}
    with pytest.raises(AppError): routing.assignees(p,a,'e','w')
