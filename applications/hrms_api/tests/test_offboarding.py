from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace

import pytest

from hrms_app.errors import AppError
from hrms_app.offboarding import OffboardingService, cutoff, validate_clearances
from hrms_app.offboarding_catalog import definition
from hrms_app.offer_documents import digest
from hrms_app.platform import Actor
from hrms_app.policy import permission_key


class Op:
    def __init__(self): self.progress, self.result = {}, None
    def checkpoint(self, **values): self.progress.update(values)
    def finish(self, result): self.result = result


class Journal:
    def __init__(self): self.ops = {}
    def lock(self, org): return nullcontext(None)
    def operation(self, db, actor, key, payload): return self.ops.setdefault(key, Op())
    def audit(self, *args): pass


@pytest.mark.parametrize('target_role', ['hrms_employee', 'hrms_office_admin', 'hrms_hr_full', 'superadmin'])
def test_employee_lookup_uses_native_access_not_target_role_name(target_role):
    employee_id = '11111111-1111-4111-8111-111111111111'
    actor = Actor('hr', 'org', 'human', frozenset({'hrms_hr_full'}),
                  frozenset({permission_key('org', 'employee:exit')}))
    record = {'organization_id': 'org', 'entity_type_id': 'employee-type',
              'data': {'platform_user_id': 'user'}}
    identity = {'id': 'user', 'role': target_role}
    calls = []
    def request(method, path, **kwargs):
        assert kwargs['token'] == 'human'
        calls.append(path)
        if path == f'/entity-records/{employee_id}':
            return record
        assert path == '/entity-types/HRMS.Employee'
        return {'entity_type_id': 'employee-type'}
    platform = SimpleNamespace(request=request, users=lambda: [identity])
    off = OffboardingService(SimpleNamespace(platform=platform, journal=None))
    assert off.employee(actor, employee_id) == (record, identity)
    assert len(calls) == 2
    denied = Actor('hr', 'org', 'human', actor.roles, frozenset())
    with pytest.raises(AppError, match='permission'):
        off.employee(denied, employee_id)
    assert len(calls) == 2
    def reject(*args, **kwargs):
        raise AppError(403, 'Native record access denied')
    platform.request = reject
    with pytest.raises(AppError, match='Native record access denied'):
        off.employee(actor, employee_id)


@pytest.fixture
def case(monkeypatch):
    monkeypatch.setattr('hrms_app.offboarding.transition_grants',lambda *a:None)
    actor = Actor('hr','org','human',frozenset(),frozenset({permission_key('org','employee:exit'),'workflow:write'}))
    day = datetime.now(UTC)-timedelta(days=1)
    values = dict(employee_id='employee',confirmed_last_day=day.date().isoformat(),access_cutoff=day.isoformat(),exit_type='Resignation',handover_owner='HR',employee_notification_email='employee@example.com',notification_email_confirmed='Yes')
    employee = {'entity_id':'employee','data':{'employment_status':'active'}}
    identity = {'id':'user','status':'active'}
    item = dict(entity_id='case',values=values,values_hash=digest(values),state='Notice & handover',workflow={'id':'workflow','machine_name':'hrms_offboarding','definition':definition()},actions=[{'trigger':'confirm_departure'}])
    writes=[]
    def write(method,path,**kwargs):
        writes.append((method,path,kwargs))
        if path=='/entity-records/employee': employee['data'].update(deepcopy(kwargs['json']['data']))
        if path=='/entity-records/case':
            item['values'].update(deepcopy(kwargs['json']['data']));item['values_hash']=digest(item['values'])
        return {}
    platform=SimpleNamespace(call=write,users=lambda:[identity])
    def end_access(op, uid, status):
        identity['status']='suspended';op.checkpoint(suspend_requested=True)
    service=SimpleNamespace(platform=platform,journal=Journal(),_end_access=end_access)
    off=OffboardingService(service)
    off.detail=lambda a,e:deepcopy(item)
    off.employee=lambda a,e:(deepcopy(employee),deepcopy(identity))
    def call(a,method,path,**kwargs):
        if path.endswith('/preflight'): return {'allowed':True}
        if path.endswith('/transitions'):
            item['state']='Departure confirmed'
            return {'to_state':item['state']}
        return {}
    off.call=call
    payload={'trigger':'confirm_departure','expected_hash':digest(values),'idempotency_key':'test-departure'}
    return off,actor,payload,item,employee,identity,writes


def test_departure_suspends_account_and_preserves_employee(case):
    off,actor,payload,item,employee,identity,writes=case
    off.act(actor,'case',payload)
    assert employee['data']['employment_status']=='offboarded'
    assert identity['status']=='suspended'
    assert item['state']=='Departure confirmed'
    assert item['values']['departure_verified']=='yes'
    count=len(writes)
    off.act(actor,'case',payload)
    assert len(writes)==count


def test_future_cutoff_does_not_suspend(case):
    off,actor,payload,item,employee,identity,writes=case
    item['values']['access_cutoff']=(datetime.now(UTC)+timedelta(days=1)).isoformat()
    payload['expected_hash']=item['values_hash']=digest(item['values'])
    with pytest.raises(AppError,match='not been reached'): off.act(actor,'case',payload)
    assert not writes and identity['status']=='active'


def test_native_rejection_prevents_side_effects(case):
    off,actor,payload,item,employee,identity,writes=case
    off.call=lambda *a,**kw:{'allowed':False,'blocked_reasons':['Manager approval required']}
    with pytest.raises(AppError,match='Manager approval'): off.act(actor,'case',payload)
    assert not writes and identity['status']=='active'


def test_stale_action_rejected(case):
    off,actor,payload,item,employee,identity,writes=case
    payload['expected_hash']='stale'
    with pytest.raises(AppError,match='changed'): off.act(actor,'case',payload)
    assert not writes


def test_unprivileged_actor_rejected(case):
    off,actor,payload,*_=case
    actor=Actor('employee','org','human',frozenset(),frozenset())
    with pytest.raises(AppError,match='permission'): off.act(actor,'case',payload)


def test_failed_transition_can_resume_without_reactivating(case):
    off,actor,payload,item,employee,identity,writes=case
    original=off.call
    def fail(a,method,path,**kw):
        if path.endswith('/transitions'): raise AppError(503,'Temporary failure')
        return original(a,method,path,**kw)
    off.call=fail
    with pytest.raises(AppError): off.act(actor,'case',payload)
    assert identity['status']=='suspended'
    off.call=original
    off.act(actor,'case',payload)
    assert item['state']=='Departure confirmed' and identity['status']=='suspended'


@pytest.mark.parametrize('value',['invalid','2026-10-22T18:00:00','2026-10-20T18:00:00+05:30'])
def test_cutoff_requires_timezone_and_valid_last_day(value):
    with pytest.raises(AppError): cutoff({'confirmed_last_day':'2026-10-22','access_cutoff':value})


def test_clearance_needs_evidence_and_all_checks():
    with pytest.raises(AppError): validate_clearances({})
    values={k:'Not applicable' for k in ['handover_status','asset_status','external_access_status','ownership_status','settlement_status']}
    with pytest.raises(AppError,match='evidence'): validate_clearances(values)
    values.update({k:'Reviewed by HR; no outstanding item' for k in ['handover_notes','asset_notes','external_access_notes','ownership_notes','settlement_notes','final_notes']})
    validate_clearances(values)


def test_notice_approval_keeps_employee_active(case):
    off,actor,payload,item,employee,identity,writes=case
    item.update(state='Pending approval',actions=[{'trigger':'approve_exit'}])
    payload['trigger']='approve_exit'
    off.act(actor,'case',payload)
    assert employee['data']['employment_status']=='active'
    assert identity['status']=='active'
    assert employee['data']['last_working_day']==item['values']['confirmed_last_day']


def test_revoked_native_transition_permission_prevents_departure(case, monkeypatch):
    off,actor,payload,item,employee,identity,writes=case
    monkeypatch.setattr('hrms_app.offboarding.transition_grants',lambda *a:set())
    with pytest.raises(AppError,match='transition permission'):
        off.act(actor,'case',payload)
    assert not writes and identity['status']=='active'


def test_withdrawal_clears_notice_without_deleting_employee(case):
    off,actor,payload,item,employee,identity,writes=case
    employee['data'].update(last_working_day='2026-10-25',exit_reason='Resignation',exit_note='Leaving')
    item.update(actions=[{'trigger':'approve_withdrawal'}])
    item['values']['change_reason']='Resignation withdrawn and approved by HR'
    payload.update(trigger='approve_withdrawal',expected_hash=digest(item['values']))
    item['values_hash']=payload['expected_hash']
    off.act(actor,'case',payload)
    assert employee['data']['employment_status']=='active'
    assert employee['data']['last_working_day'] is None
    assert identity['status']=='active'
    assert all(method!='DELETE' for method,_,_ in writes)


def test_departed_employee_cannot_withdraw(case):
    off,actor,payload,item,employee,identity,writes=case
    employee['data']['employment_status']='offboarded'
    item['actions']=[{'trigger':'approve_withdrawal'}]
    item['values']['change_reason']='Attempted withdrawal'
    payload.update(trigger='approve_withdrawal',expected_hash=digest(item['values']))
    item['values_hash']=payload['expected_hash']
    with pytest.raises(AppError,match='cannot be reactivated'):
        off.act(actor,'case',payload)
    assert not writes


def test_seed_dates_match_native_method_engine():
    graph=definition()
    date_fields={'notified_date','requested_last_day','confirmed_last_day'}
    assert all(f['type']=='datetime' for f in graph['entity_schema']['fields'] if f['field'] in date_fields)
    assert all(f['type']=='datetime' for t in graph['transitions'] for f in t['required_fields'] if f['field'] in date_fields)


def test_workflow_resolves_native_generated_identifier(case):
    off,actor,*_=case
    native={'id':'native-id','machine_name':'workflow_generated','entity_type':'HRMS.Offboarding','organization_id':'org','is_active':True}
    paths=[]
    def call(a,method,path,**kwargs):
        paths.append(path)
        return {'published_items':[native]} if path=='/workflow-state-machines' else native
    off.call=call
    assert off.workflow(actor)['machine_name']=='workflow_generated'
    assert paths==['/workflow-state-machines','/workflow-state-machines/native-id']
