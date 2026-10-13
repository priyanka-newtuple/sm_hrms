"""Remove only uniquely marked local onboarding smoke fixtures via public native APIs."""
import json, os, re, sys
import httpx
from hrms_app.platform import PlatformClient
org=os.environ['HRMS_ORGANIZATION_ID']
assert org=='11111111-1111-1111-1111-111111111111'
assert os.environ['PLATFORM_API_URL']=='http://platform-api:8000/v1/api'
p=PlatformClient(os.environ['PLATFORM_API_URL'],org,os.environ['HRMS_INSTALL_EMAIL'],os.environ['HRMS_INSTALL_PASSWORD'])
rows=p.records('HRMS.OnboardingJourney',['work_email','employee_id','user_id','hrms_operation_key'])
hires=[r for r in rows if re.fullmatch(r'onboarding\.check\.[0-9a-f]{8}@newtuple\.com',r['data'].get('work_email','')) and r['data'].get('hrms_operation_key','').startswith('journey:journey-test-')]
jids={r['entity_id'] for r in hires}; eids={r['data'].get('employee_id') for r in hires}-{None,''}; uids={r['data'].get('user_id') for r in hires}-{None,''}; emails={r['data']['work_email'] for r in hires}
records=[]; files=[]
for kind in ['HRMS.OnboardingProfile','HRMS.OnboardingChecklistTask','HRMS.SalaryAccount']:
    records.extend((kind,r['entity_id']) for r in p.records(kind,['journey_id']) if r['data'].get('journey_id') in jids)
for r in p.records('HRMS.Asset',['asset_tag','asset_name','issued_employee_id']):
    if r['data'].get('asset_name')=='Onboarding verification laptop' and re.fullmatch(r'ONB-[0-9a-f]{8}',r['data'].get('asset_tag','')) and r['data'].get('issued_employee_id') in eids: records.append(('HRMS.Asset',r['entity_id']))
for id in jids:
    files.extend(d['file_id'] for d in p.call('POST','/filehandler/list',json={'owner_entity_id':id})['items'] if d.get('owner_entity_id')==id and d['organization_id']==org)
records.extend(('HRMS.OnboardingJourney',id) for id in jids)
for r in p.records('HRMS.Employee',['work_email']):
    if r['entity_id'] in eids and r['data'].get('work_email') in emails: records.append(('HRMS.Employee',r['entity_id']))
users=[u for u in p.users() if u['id'] in uids and u['email'] in emails]
print(json.dumps({'hires':sorted(emails),'records':len(records),'files':len(files),'users':len(users)},indent=2))
if '--apply' not in sys.argv: sys.exit()
for id in files: p.call('DELETE','/filehandler/'+id)
for kind,id in records: p.call('DELETE','/entity-records/'+id)
root=p.request('POST','/auth/login',json={'email':os.environ['HRMS_PLATFORM_OWNER_EMAIL'],'password':os.environ['HRMS_PLATFORM_OWNER_PASSWORD']})['access_token']
for u in users: p.request('DELETE',f'/organizations/{org}/users/{u["id"]}',token=root)
inbox=httpx.Client(base_url='http://local-mail:8025',timeout=20)
messages=inbox.get('/api/v1/messages',params={'limit':1000}).json()['messages']
ids=[m['ID'] for m in messages if any(t['Address'] in emails for t in m['To'])]
if ids:
    r=inbox.request('DELETE','/api/v1/messages',json={'IDs':ids});r.raise_for_status()
print('Removed marked fixture records, native users, documents and captured emails. Native audit history retained.')
