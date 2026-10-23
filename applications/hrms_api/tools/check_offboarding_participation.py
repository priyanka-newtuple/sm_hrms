"""Isolated local smoke test; creates and archives only its own disposable records."""
import os
import time
from uuid import uuid4
from hrms_app.platform import PlatformClient
from hrms_app.service import HrmsService
from hrms_app.journal import Journal
from hrms_app.offboarding import OffboardingService
from hrms_app.offboarding_participation import EmployeeOffboarding
from hrms_app.errors import AppError

assert os.environ['PLATFORM_API_URL']=='http://platform-api:8000/v1/api'
assert os.environ['HRMS_ORGANIZATION_ID']=='11111111-1111-1111-1111-111111111111'
def client(prefix):
    return PlatformClient(os.environ['PLATFORM_API_URL'],os.environ['HRMS_ORGANIZATION_ID'],os.environ[prefix+'_EMAIL'],os.environ[prefix+'_PASSWORD'])
admin=client('HRMS_INSTALL'); runtime=client('HRMS_SERVICE')
assert admin.call('GET',f'/integrations/organizations/{admin.org}/smtp')['config']['smtp_host']=='local-mail'
actor=admin.actor(admin.service_token())
service=HrmsService(runtime,Journal(os.environ['HRMS_APP_DATABASE_URL']),'newtuple.com')
off=OffboardingService(service); mine=EmployeeOffboarding(off)
uid=eid=xid=None
try:
    tag=uuid4().hex[:10]; email=f'offboarding-smoke-{tag}@newtuple.com'; password=uuid4().hex+'Aa1!'
    uid=admin.request('POST','/auth/register',json={'email':email,'full_name':'Offboarding Smoke','password':password,'role':'hrms_employee'})['user_id']
    admin.call('POST',f'/users/{uid}/approve')
    role=next(r for r in admin.call('GET','/roles') if r['name']=='hrms_employee')
    admin.call('PUT',f'/roles/users/{uid}/role',json={'role_id':role['id']})
    employee_client=PlatformClient(os.environ['PLATFORM_API_URL'],admin.org,email,password)
    employee_actor=employee_client.actor(employee_client.service_token())
    eid=admin.create_record('HRMS.Employee',dict(employee_code='SMOKE-'+tag,first_name='Offboarding',last_name='Smoke',work_email=email,platform_user_id=uid,department='Test',designation='Test',employment_status='active',hrms_role='hrms_employee',hrms_operation_key='offboarding-smoke:'+tag),uid)['entity_id']
    values=dict(employee_id=eid,exit_type='Resignation',notified_date='2026-10-23',requested_last_day='2026-11-30',confirmed_last_day='2026-11-30',exit_reason='Local smoke test',offboarding_approver_id=actor.user_id,offboarding_coordinator_id=actor.user_id,employee_notification_email=email,notification_email_confirmed='Yes')
    xid=off.save(actor,dict(values=values,idempotency_key=uuid4().hex,expected_hash=''))['entity_id']
    assert not mine.rows(employee_actor)
    print('Draft private: PASS',flush=True)
    def act(trigger):
        item=off.detail(actor,xid)
        off.act(actor,xid,dict(trigger=trigger,values={},expected_hash=item['values_hash'],idempotency_key=uuid4().hex))
    act('submit_for_approval')
    assert mine.detail(employee_actor,xid)['state']=='Pending approval'
    item=off.detail(actor,xid)
    off.save(actor,dict(values={'handover_owner':'Test HR coordinator','change_reason':'Set planned access cutoff','access_cutoff':'2026-11-30T18:00:00+05:30'},expected_hash=item['values_hash'],idempotency_key=uuid4().hex),xid)
    act('approve_exit')
    for _ in range(20):
        item=mine.detail(employee_actor,xid)
        if item['editable']:break
        time.sleep(1)
    assert item['editable'], 'Native employee assignment did not complete'
    assert not {'exit_reason','hr_notes','employee_notification_email'} & item['values'].keys()
    print('Native assignment and safe employee projection: PASS',flush=True)
    mine.command(employee_actor,xid,dict(values={'employee_handover_notes':'Test handover','employee_asset_notes':'No assets','employee_handover_confirmed':'Yes'},expected_hash=item['values_hash'],idempotency_key=uuid4().hex))
    item=mine.detail(employee_actor,xid)
    mine.command(employee_actor,xid,dict(trigger='submit_employee_handover',values={},expected_hash=item['values_hash'],idempotency_key=uuid4().hex))
    assert mine.detail(employee_actor,xid)['state']=='Notice & handover'
    assert not mine.detail(employee_actor,xid)['editable']
    print('Employee submission and return to HR: PASS',flush=True)
finally:
    for rid in (xid,eid):
        if rid:
            admin.call('DELETE',f'/entity-records/{rid}')
    if uid:admin.call('POST',f'/users/{uid}/suspend')
    print('Disposable records archived; test account suspended',flush=True)
    admin.close();runtime.close()
