from copy import deepcopy
from types import SimpleNamespace

import pytest
from hrms_app.employee_lifecycle import (
    APPROVAL_TAG,
    COMPLETE_TAG,
    ONBOARDING_ROLE,
    reconcile_employee,
)
from hrms_app.errors import AppError
from test_performance import Journal


class Platform:
    org = "org"

    def __init__(self):
        self.data = {
            "first_name": "New",
            "last_name": "Employee",
            "work_email": "new@newtuple.com",
            "hrms_role": "hrms_employee",
        }
        self.people = []
        self.writes = []
        self.email_fails = False

    def record(self, eid):
        return {"organization_id": self.org, "data": deepcopy(self.data)}

    def users(self):
        return deepcopy(self.people)

    def request(self, method, path, **kwargs):
        self.writes.append((path, kwargs["json"]))
        if path == "/auth/register":
            self.people.append(
                {
                    "id": "user",
                    "organization_id": self.org,
                    "email": self.data["work_email"],
                    "status": "pending",
                }
            )
            return {
                "user_id": "user",
                "organization_id": self.org,
                "approval_type": "pending_org_admin",
            }
        if path == "/auth/forgot-password":
            if self.email_fails:
                raise AppError(503, "Unknown delivery outcome")
            return {"message": "Requested"}
        raise AssertionError(path)

    def call(self, method, path, **kwargs):
        if path == "/roles":
            return [{"id": r, "name": r} for r in [ONBOARDING_ROLE, "hrms_employee"]]
        self.writes.append((path, kwargs["json"]))
        if path == "/entity-records/employee":
            self.data.update(kwargs["json"]["data"])
        if path == "/entities/employee/transitions":
            self.data.update(kwargs["json"]["inputs"])


def system():
    p = Platform()
    s = SimpleNamespace(platform=p, journal=Journal(), domain="newtuple.com")
    w = {
        "id": "workflow",
        "definition": {"transitions": [{"from": "Approval", "trigger": "approved"}]},
    }
    e = {"entity_id": "employee", "current_state": "Approval"}
    return p, s, w, e


def test_pending_native_account_waits_for_approval_then_invites_once_and_grants_role_only_at_completion():
    p, s, w, e = system()
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    assert len(p.people) == 1
    assert p.data["platform_user_id"] == "user"
    assert not p.data.get("account_approved")
    assert not any(path.endswith("/transitions") for path, _ in p.writes)
    p.people[0]["status"] = "active"
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    assert sum(path == "/auth/forgot-password" for path, _ in p.writes) == 1
    assert p.data["account_approved"] is True
    assert not any(body.get("role_id") == "hrms_employee" for _, body in p.writes)
    reconcile_employee(s, w, e, [COMPLETE_TAG])
    reconcile_employee(s, w, e, [COMPLETE_TAG])
    assert sum(body.get("role_id") == "hrms_employee" for _, body in p.writes) == 1


def test_unknown_invitation_outcome_does_not_repeat_or_advance():
    p, s, w, e = system()
    reconcile_employee(s, w, e, [APPROVAL_TAG])
    p.people[0]["status"] = "active"
    p.email_fails = True
    with pytest.raises(AppError):
        reconcile_employee(s, w, e, [APPROVAL_TAG])
    with pytest.raises(AppError):
        reconcile_employee(s, w, e, [APPROVAL_TAG])
    assert sum(path == "/auth/forgot-password" for path, _ in p.writes) == 1
    assert not p.data.get("account_approved")


def test_existing_email_is_never_silently_taken_over():
    p, s, w, e = system()
    p.people = [
        {
            "id": "existing",
            "email": p.data["work_email"],
            "organization_id": p.org,
            "status": "active",
        }
    ]
    with pytest.raises(AppError):
        reconcile_employee(s, w, e, [APPROVAL_TAG])
    assert not p.writes

def test_profile_assignee_uses_linked_account_and_releases_after_submission(monkeypatch):
    from hrms_app.employee_lifecycle import reconcile_profile_assignee
    monkeypatch.setenv('HRMS_EMPLOYEE_PROFILE_FORM_ID', 'profile-form')
    writes = []
    record = {'organization_id': 'org', 'data': {'platform_user_id': 'employee-user'}, 'assignee_id': None}
    p = SimpleNamespace(org='org', record=lambda _: record,
                        call=lambda method, path, **kw: writes.append(kw['json']))
    workflow = {'definition': {'states': [{'name': 'Profile', 'method_refs': [{'method_id': 'profile-form'}]}]}}
    row = {'entity_id': 'employee', 'current_state': 'Profile'}
    reconcile_profile_assignee(p, workflow, row)
    assert writes == [{'assignee_id': 'employee-user'}]
    record['assignee_id'] = 'employee-user'
    reconcile_profile_assignee(p, workflow, row)
    assert len(writes) == 1
    row['current_state'] = 'Provisioning'
    reconcile_profile_assignee(p, workflow, row)
    assert writes[-1] == {'assignee_id': None}
    record['assignee_id'] = 'office-admin'
    reconcile_profile_assignee(p, workflow, row)
    assert len(writes) == 2


def test_final_signoff_assigns_initiating_hr_and_does_not_clear_on_poll(monkeypatch):
    monkeypatch.setenv("HRMS_EMPLOYEE_SIGNOFF_FORM_ID", "signoff-form")
    from hrms_app.employee_lifecycle import reconcile_profile_assignee
    writes = []
    record = {'organization_id': 'org', 'owner_id': 'hr-creator',
              'data': {'platform_user_id': 'employee-user'}, 'assignee_id': None}
    def call(method, path, **kw):
        writes.append(kw['json'])
        record.update(kw['json'])
    p = SimpleNamespace(org='org', record=lambda _: record, call=call)
    w = {'definition': {'states': [{'name': 'Final review', 'method_refs': [{'method_id':'signoff-form'}]}]}}
    e = {'entity_id': 'employee', 'current_state': 'Final review'}
    reconcile_profile_assignee(p,w,e)
    reconcile_profile_assignee(p,w,e)
    assert writes == [{'assignee_id': 'hr-creator'}]
    record['owner_id'] = None
    with pytest.raises(AppError):
        reconcile_profile_assignee(p,w,e)


def test_final_hr_signoff_does_not_grant_portal_access_before_completion():
    p,s,w,e=system()
    p.data['platform_user_id']='user'
    p.people=[{'id':'user','email':p.data['work_email'],'organization_id':'org','status':'active'}]
    e['current_state']='Final HR Sign-off'
    reconcile_employee(s,w,e,[])
    assert not any(body.get('role_id') == 'hrms_employee' for _,body in p.writes)
    e['current_state']='Onboarding Completed'
    reconcile_employee(s,w,e,[COMPLETE_TAG])
    assert sum(body.get('role_id') == 'hrms_employee' for _,body in p.writes)==1
