"""Opt-in native asset relationship setup; never republishes Employee workflows."""
import argparse,json,os
from pathlib import Path
import httpx

def configure(base_url, token, organization_id, backup_dir, form_id):
    backup=Path(backup_dir);backup.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url=base_url.rstrip('/')+'/',headers={'Authorization':'Bearer '+token},timeout=60) as c:
        def api(method,path,**kw):
            r=c.request(method,path.lstrip('/'),**kw);r.raise_for_status();return r.json()
        def save(name,value):
            p=backup/name
            if not p.exists():p.write_text(json.dumps(value,indent=2))
        assert api('GET','/organizations/current')['id']==organization_id
        save('workflows-before.json',api('GET','/workflow-state-machines',params={'scope':'published'}))
        asset=api('GET','/entity-types/HRMS.Asset')['entity_type_id']
        employee=api('GET','/entity-types/HRMS.Employee')['entity_type_id']
        relations=api('GET',f'/entity-types/{asset}/relations')['items']
        if not any(r['to_entity_type_id']==employee and r['relation_name']=='ISSUED_TO' for r in relations):
            api('POST',f'/entity-types/{asset}/relations',json={'to_entity_type_id':employee,'relation_name':'ISSUED_TO'})
        form=api('GET','/method-library/methods/'+form_id)
        save('form-before.json',form)
        description=(form['identity'].get('description') or '')
        note='HRMS displays issued_asset_references as linked assets and fills its transition evidence from Asset records. GitHub, Slack and subscription fields remain unchanged.'
        if note not in description:
            api('PATCH','/method-library/methods/'+form_id,json={'description':(description+'\n'+note).strip()})
        assert api('GET','/method-library/methods/'+form_id)['fields']==form['fields']
        assert api('GET','/workflow-state-machines',params={'scope':'published'})==json.loads((backup/'workflows-before.json').read_text())
        print('Native ISSUED_TO relationship configured; form metadata updated; fields and workflows unchanged.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['base-url','organization-id','backup-dir','form-id']:p.add_argument('--'+name,required=True)
    a=p.parse_args();configure(a.base_url,os.environ['HRMS_SETTINGS_TOKEN'],a.organization_id,a.backup_dir,a.form_id)
