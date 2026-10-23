"""Install native offboarding through public APIs; never replace tenant edits."""
import os
import psycopg
from .errors import AppError
from .offboarding_catalog import ENTITY, MACHINE, FIELDS, SECTIONS, SYSTEM_FIELDS, definition
from .platform import PlatformClient


def install(api, dsn):
    try:
        api.call('GET', '/entity-types/' + ENTITY)
    except AppError as e:
        if e.status != 404:
            raise
        api.call('POST', '/entity-types', json={'organization_id': api.org, 'name': ENTITY,
            'description': 'Employee exit and clearance record', 'schema_definition': {'fields': FIELDS, 'identifier_template': 'EXT-{{seq}}'}, 'version': 1})
    try:
        published=api.call('GET','/workflow-state-machines',params={'scope':'published'})['published_items']
        matches=[w for w in published if w['entity_type']==ENTITY and w['is_active']]
        if len(matches)>1:
            raise AppError(409,'Offboarding needs exactly one active native workflow')
        if not matches:
            raise AppError(404,'Offboarding is not installed')
        workflow=api.call('GET',f"/workflow-state-machines/{matches[0]['id']}")
    except AppError as e:
        if e.status != 404:
            raise
        types = api.call('GET', '/field-library/field-types')['items']
        methods = {}
        for title, fields in {**SECTIONS, 'Exit verification': SYSTEM_FIELDS}.items():
            links = []
            for f in fields:
                key = f['field']
                found = next((x for x in api.call('GET','/field-library/fields',params={'search':key,'limit':200})['items'] if x['identity']['field_key']==key), None)
                if not found:
                    engine = 'datetime' if f['type']=='date' else f['type']
                    code = next(t['code'] for t in types if t['engine_type']==engine and t['selectable'])
                    settings = {k:f[k] for k in ('enum_values','read_only') if k in f}
                    if engine=='document':
                        settings['document_config']={'type_id':'generic_document','multiple':True}
                    found=api.call('POST','/field-library/fields',json={'name':f['description'],'field_key':key,'field_type':code,'settings':settings})
                links.append({'library_field_id':found['identity']['library_field_id'],'version_id':found['version']['version_id'], 'label':f['description'],'required':f.get('required',False)})
            existing=api.call('GET','/method-library/methods',params={'entity_type':ENTITY,'limit':200})['items']
            method=next((m for m in existing if m['name']=='Offboarding · '+title),None)
            if not method:
                method=api.call('POST','/method-library/methods',json={'name':'Offboarding · '+title,'entity_types':[ENTITY],'fields':links})['identity']
            methods[title]=method['method_id']
        graph=definition()
        graph['entity_schema']['fields']=[]
        for state in graph['states']:
            titles=['Exit details','Exit verification']
            if state['name'] in {'Pending approval','Notice & handover','Departure confirmed','Final clearance','Completed'}:
                titles.append('Handover and clearances')
            if state['name'] in {'Final clearance','Completed'}:
                titles.append('Final HR review')
            state['method_refs']=[{'method_id':methods[t]} for t in titles]
        validation=api.call('POST','/workflow-state-machines/validate',json={'machine_name':MACHINE,'definition':graph})
        if not validation.get('can_publish'):
            raise AppError(422, str(validation.get('validation_report')))
        drafts=api.call('GET','/workflow-state-machines',params={'scope':'draft'})['draft_items']
        draft=next((d for d in drafts if d['name']=='Employee offboarding'),None)
        if not draft:
            draft=api.call('POST','/workflow-state-machines/draft',json={'name':'Employee offboarding'})
        workflow=api.call('POST',f"/workflow-state-machines/{draft['id']}/publish",json={'definition':graph})['state_machine']
    from .install_offboarding_participation import install as install_participation
    workflow=install_participation(api,dsn,workflow)
    machine=workflow['machine_name']
    catalog=api.call('GET','/workflow-state-machines',params={'scope':'all'})
    existing_machines={w['machine_name'] for w in catalog['published_items']+catalog['draft_items']}
    # App-owned installation marker preserves later native permission revocations.
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS hrms_feature_setup (organization_id text, feature text, PRIMARY KEY (organization_id, feature))')
        installed = bool(db.execute('SELECT 1 FROM hrms_feature_setup WHERE organization_id=%s AND feature=%s',(api.org,'offboarding-v1')).fetchone())
        for role in api.call('GET','/roles'):
            if role['name'] not in {'superadmin','hrms_hr_full','hrms_application_service'}:
                continue
            r=api.call('GET',f"/roles/{role['id']}")
            service=role['name']=='hrms_application_service'
            if installed and not service:
                continue
            entities=[{k:p[k] for k in ('entity_type','action','allowed','entity_field','operator','value_source','condition_value','read_filter') if k in p} for p in r['entity_permissions'] if p['entity_type']!=ENTITY]
            entities += [{'entity_type':ENTITY,'action':a} for a in ('view','create','edit')]
            configured_fields = {f['field']:f for f in FIELDS}
            configured_fields.update({f['field']:f for f in workflow['definition']['entity_schema']['fields']})
            fields=[{k:p[k] for k in ('entity_type','field_name','can_view','can_edit','mask_value')} for p in r['field_permissions'] if p['entity_type']!=ENTITY or (p['field_name'] not in configured_fields and p['field_name']!='identifier')]
            fields += [dict(entity_type=ENTITY,field_name=f['field'],can_view=True,can_edit=service or f['field'] not in {x['field'] for x in SYSTEM_FIELDS+SECTIONS['Employee handover']},mask_value=False) for f in configured_fields.values()]
            fields.append(dict(entity_type=ENTITY,field_name='identifier',can_view=True,can_edit=True,mask_value=False))
            # Retired workflow references cannot be resubmitted to native RBAC.
            # Preserve every grant for workflows that still exist.
            workflows=[{'machine_name':p['machine_name']} for p in r['workflow_permissions'] if p['machine_name']!=machine and p['machine_name'] in existing_machines]+[{'machine_name':machine}]
            transitions=[{k:p[k] for k in ('machine_name','transition_key')} for p in r['transition_permissions'] if p['machine_name']!=machine and p['machine_name'] in existing_machines]
            transitions += [{'machine_name':machine,'transition_key':t['key']} for t in workflow['definition']['transitions'] if service or t['trigger']!='submit_employee_handover']
            api.call('PUT',f"/roles/{role['id']}",json={'entity_permissions':entities,'field_permissions':fields,'workflow_permissions':workflows,'transition_permissions':transitions})
        db.execute('INSERT INTO hrms_feature_setup VALUES (%s,%s) ON CONFLICT DO NOTHING',(api.org,'offboarding-v1'))


if __name__=='__main__':
    client=PlatformClient(os.environ['PLATFORM_API_URL'],os.environ['HRMS_ORGANIZATION_ID'],os.environ['HRMS_INSTALL_EMAIL'],os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        install(client,os.environ['HRMS_APP_DATABASE_URL'])
        print('Native offboarding configuration installed')
    finally:
        client.close()
