"""Explicit native Settings update: verify employee details before IT provisioning.

Uses a human Settings token. Existing pinned enrollments are not reset or migrated.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import runpy

import httpx


def configure(base_url, token, organization_id, machine_name, backup_dir):
    with httpx.Client(base_url=base_url.rstrip('/')+'/', headers={'Authorization':'Bearer '+token}, timeout=60) as client:
        def api(method,path,**kwargs):
            r=client.request(method,path.lstrip('/'),**kwargs)
            r.raise_for_status()
            return r.json()
        if api('GET','/organizations/current')['id'] != organization_id:
            raise RuntimeError('Wrong tenant')
        backup=Path(backup_dir);backup.mkdir(parents=True,exist_ok=True)
        def save(name,value):
            path=backup/name
            if not path.exists():path.write_text(json.dumps(value,indent=2),encoding='utf-8')
        w=next(w for w in api('GET','/workflow-state-machines',params={'scope':'published'})['published_items'] if w['machine_name']==machine_name and w['is_active'])
        save('workflow-before.json',w)
        d=copy.deepcopy(w['definition'])
        profile='Profile Completion Pending';verify='Onboarding Verification';it='IT & Workspace Provisioning';complete='Onboarding Completed'
        order=['Employee Registration','Email Setup','Account Approval',profile,verify,it,complete]
        if set(order)!={s['name'] for s in d['states']}:
            raise RuntimeError('Review unexpected states before updating the sequence')
        d['states'].sort(key=lambda s:order.index(s['name']))
        for i,s in enumerate(d['states']):s['order']=i+1
        for source,destination,key,label in [(profile,verify,'profile_to_verification','Submit profile for verification'),(verify,it,'verification_to_provisioning','Approve details and send to IT'),(it,complete,'provisioning_to_completed','Complete provisioning and onboarding')]:
            old=next(t for t in d['transitions'] if t['from']==source and t['key'] not in {'request_profile_changes','request_provisioning_changes'})
            old.update(key=key,trigger=key,to_state=destination,label=label)
        d['transitions']=[t for t in d['transitions'] if t['key']!='request_provisioning_changes']
        correction=next(t for t in d['transitions'] if t['key']=='request_profile_changes')
        correction.update(label='Request employee corrections',to_state=profile)
        draft=api('POST',f'/workflow-state-machines/{machine_name}/draft',json={'definition':d})
        api('PUT',f"/workflow-state-machines/{draft['id']}/draft",json={'definition':d})
        d=api('GET',f"/workflow-state-machines/{draft['id']}")['definition']
        report=api('POST','/workflow-state-machines/validate',json={'machine_name':machine_name,'definition':d})
        save('validation.json',report)
        if not report['can_publish']:raise RuntimeError(json.dumps(report['validation_report']))
        published=api('POST',f"/workflow-state-machines/{draft['id']}/publish",json={'definition':d})['state_machine']
        save('published.json',published)
        runpy.run_path(str(Path(__file__).with_name('configure-hrms-onboarding-returns.py')))['configure_roles'](api,save,published)
        print(json.dumps({'workflow_id':published['id'],'version':published['version'],'sequence':order}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['base-url','organization-id','machine-name','backup-dir']:p.add_argument('--'+name,required=True)
    a=p.parse_args()
    configure(a.base_url,os.environ['HRMS_SETTINGS_TOKEN'],a.organization_id,a.machine_name,a.backup_dir)
