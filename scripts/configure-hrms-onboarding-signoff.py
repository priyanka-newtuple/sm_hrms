"""Explicit native Settings update: add initiating-HR sign-off after IT provisioning.

Uses a human Settings token. Existing pinned enrollments are not reset or migrated.
"""
import argparse
import copy
import json
import os
from pathlib import Path

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
        final='Final HR Sign-off'
        if any(s['name']==final for s in d['states']):
            raise RuntimeError('Final HR sign-off already exists; inspect before changing it')
        it='IT & Workspace Provisioning'; complete='Onboarding Completed'
        old=next(t for t in d['transitions'] if t['from']==it and t['to_state']==complete)
        final_state=copy.deepcopy(next(s for s in d['states'] if s['name']=='Onboarding Verification'))
        final_state.update(name=final, description='The HR user who registered this employee confirms final onboarding completion.',
                           tags=[], on_state_actions=[])
        ref=final_state['method_refs'][0]
        form_path=backup/'signoff-form.json'
        if form_path.exists():
            form=json.loads(form_path.read_text())
        else:
            form=api('POST',f"/method-library/methods/{ref['method_id']}/clone",json={'name':'Employee Final HR Sign-off','source_version_id':ref['version_id']})
            save('signoff-form.json',form)
        final_state['method_refs']=[{'method_id':form['identity']['method_id'],'version_id':form['version']['version_id']}]
        d['states'].insert(next(i for i,s in enumerate(d['states']) if s['name']==complete),final_state)
        for i,s in enumerate(d['states']):s['order']=i+1
        order=[s['name'] for s in d['states']]
        old.update(key='provisioning_to_hr_signoff',trigger='provisioning_to_hr_signoff',to_state=final,
                   label='Finish IT provisioning and send to HR', description='Send completed provisioning to the HR user who started onboarding.')
        d['transitions'].append({'key':'hr_signoff_to_completed','trigger':'hr_signoff_to_completed',
                                'from':final,'to_state':complete,'label':'Mark onboarding complete',
                                'description':'Final confirmation by the initiating HR user.',
                                'guards':[],'required_fields':[]})
        draft=api('POST',f'/workflow-state-machines/{machine_name}/draft',json={'definition':d})
        api('PUT',f"/workflow-state-machines/{draft['id']}/draft",json={'definition':d})
        d=api('GET',f"/workflow-state-machines/{draft['id']}")['definition']
        report=api('POST','/workflow-state-machines/validate',json={'machine_name':machine_name,'definition':d})
        save('validation.json',report)
        if not report['can_publish']:raise RuntimeError(json.dumps(report['validation_report']))
        published=api('POST',f"/workflow-state-machines/{draft['id']}/publish",json={'definition':d})['state_machine']
        save('published.json',published)
        for role in api('GET','/roles'):
            if role['name'] not in {'hrms_hr_full','hrms_office_admin'}:continue
            detail=api('GET','/roles/'+role['id'])
            save('role-before-'+role['name']+'.json',detail)
            tp=[{k:p[k] for k in ['machine_name','transition_key']} for p in detail['transition_permissions']]
            key='hr_signoff_to_completed' if role['name']=='hrms_hr_full' else 'provisioning_to_hr_signoff'
            grant={'machine_name':machine_name,'transition_key':key}
            if grant not in tp:tp.append(grant)
            api('PUT','/roles/'+role['id'],json={'transition_permissions':tp})
        print(json.dumps({'workflow_id':published['id'],'version':published['version'],'sequence':order}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['base-url','organization-id','machine-name','backup-dir']:p.add_argument('--'+name,required=True)
    a=p.parse_args()
    configure(a.base_url,os.environ['HRMS_SETTINGS_TOKEN'],a.organization_id,a.machine_name,a.backup_dir)
