"""Versioned native configuration migration; no platform database writes."""
from copy import deepcopy
import os
import psycopg
from .errors import AppError
from .offboarding_catalog import ENTITY, SECTIONS, SYSTEM_FIELDS, FIELDS
from .offboarding_checklist import CHECKLIST, METADATA, EMPLOYEE_KEYS, EMPLOYEE_TRIGGERS, definition, STAGES


def install(api, dsn, workflow):
    feature = 'offboarding-checklist-v2'
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute('SELECT pg_advisory_lock(hashtextextended(%s, 0))',(api.org+':offboarding-checklist-v2',))
        if db.execute('SELECT 1 FROM hrms_feature_setup WHERE organization_id=%s AND feature=%s',(api.org,feature)).fetchone():
            return
        machine = workflow['machine_name']
        drafts = api.call('GET','/workflow-state-machines',params={'scope':'draft','machine_name':machine})['draft_items']
        reusable_draft = None
        def canonical(value):
            value = deepcopy(value)
            for transition in value.get('transitions', []):
                if 'from_state' in transition:
                    transition['from'] = transition.pop('from_state')
            return value
        if drafts:
            if len(drafts) != 1:
                raise AppError(409,'Resolve the existing offboarding drafts before installing the checklist workflow')
            reusable_draft = api.call('GET','/workflow-state-machines/'+drafts[0]['id'])
            if canonical(reusable_draft['definition']) != canonical(workflow['definition']):
                raise AppError(409,'Resolve the existing offboarding draft before installing the checklist workflow')
        known = {'Draft','Pending approval','Changes requested','Employee handover','Notice & handover','Departure confirmed','Final clearance','Completed','Cancelled','Discarded'}
        if any(s['name'] not in known | set(STAGES) for s in workflow['definition']['states']):
            raise AppError(409,'Customized offboarding stages require a reviewed checklist migration')
        if workflow['definition']['initial_state']!='Not Started':
            known_fields={f['field'] for f in FIELDS}|{'identifier'}
            extra={f['field'] for f in workflow['definition']['entity_schema']['fields']}-known_fields
            known_triggers={'submit_for_approval','resubmit','request_changes','approve_exit','confirm_departure','start_final_clearance','complete_offboarding','cancel_request','approve_withdrawal','submit_employee_handover','request_employee_handover'}
            if extra or any(t['trigger'] not in known_triggers for t in workflow['definition']['transitions']) or any(s.get('sla') for s in workflow['definition']['states']):
                raise AppError(409,'Custom offboarding fields, transitions or SLA rules require a reviewed migration')
        from .install_offboarding_notifications import install as install_notifications
        install_notifications(api)
        forms = {
            'Exit administration': [f for f in SECTIONS['Exit details'] if f['field']!='offboarding_approver_id'] + SYSTEM_FIELDS + [f for f in METADATA if not f['field'].startswith('exit_')],
            **CHECKLIST,
            'Clearance verification': SECTIONS['Handover and clearances'] + SECTIONS['Final HR review'],
        }
        fields = {f['field']:f for group in forms.values() for f in group}
        entity = api.call('GET','/entity-types/'+ENTITY)
        schema = deepcopy(entity['schema_definition'])
        existing = {f['field'] for f in schema['fields']}
        schema['fields'] += [dict(f,required=False) for key,f in fields.items() if key not in existing]
        if schema != entity['schema_definition']:
            api.call('PUT','/entity-types/'+ENTITY,json={'schema_definition':schema})
        types = api.call('GET','/field-library/field-types')['items']
        methods = {}
        for title, group in forms.items():
            links = []
            for f in group:
                # Namespaced library identities avoid altering shared/legacy fields.
                found = next((x for x in api.call('GET','/field-library/fields',params={'search':f['field'],'limit':200})['items'] if x['identity']['field_key']==f['field']),None)
                if not found:
                    code = next(t['code'] for t in types if t['engine_type']==f['type'] and t['selectable'])
                    settings = {k:f[k] for k in ('enum_values',) if k in f}
                    if f['type']=='document': settings['document_config']={'type_id':'generic_document','multiple':True}
                    found = api.call('POST','/field-library/fields',json={'name':'Exit checklist v2 - '+f['field'],'field_key':f['field'],'field_type':code,'settings':settings})
                links.append({'library_field_id':found['identity']['library_field_id'],'version_id':found['version']['version_id'],'label':f['description'],'required':False})
            name = 'Exit checklist v2 · '+title
            method = next((m for m in api.call('GET','/method-library/methods',params={'entity_type':ENTITY,'limit':200})['items'] if m['name']==name),None)
            if not method:
                method = api.call('POST','/method-library/methods',json={'name':name,'entity_types':[ENTITY],'fields':links})['identity']
            methods[title] = method['method_id']
        templates = {}
        existing_templates = api.call('GET','/email-templates')['items']
        for stage in STAGES:
            name = 'Exit checklist v2 · '+stage
            template = next((t for t in existing_templates if t['name']==name),None)
            if not template:
                template = api.call('POST','/email-templates',json={'name':name,'entity_type':ENTITY,'subject':'MyHub offboarding · {{employee_code}} · '+stage,
                    'body_html':'<p>Your offboarding case is now <strong>'+stage+'</strong>.</p><p><a href="{{workspace_url}}">Open MyHub tasks</a> to view progress and your assigned actions. HR can review the case in HR Cockpit. If access has ended, contact your HR coordinator.</p><p>Feedback and confidential clearance details are available only in the authenticated application. If corrections are requested, open the case to read the HR reason.</p>'})
            templates[stage] = template['template_id']
        graph = definition(methods,templates)
        graph['machine_key']=workflow['definition']['machine_key']
        validation = api.call('POST','/workflow-state-machines/validate',json={'machine_name':machine,'definition':graph})
        if not validation.get('can_publish'): raise AppError(422,str(validation['validation_report']))
        # Only new enrollments use the new version. No enrollment is moved here.
        if workflow['definition']['initial_state'] != 'Not Started':
            draft = reusable_draft or api.call('POST',f'/workflow-state-machines/{machine}/draft')
            api.call('POST',f"/workflow-state-machines/{draft['id']}/publish",json={'definition':graph})
        for summary in api.call('GET','/roles'):
            if summary['name'] not in {'superadmin','hrms_hr_full','hrms_application_service'}:
                role=api.call('GET','/roles/'+summary['id'])
                private={f['field'] for f in CHECKLIST['Employee Feedback & Experience']}|{'checklist_submission_history'}
                permissions=[{k:p[k] for k in ('entity_type','field_name','can_view','can_edit','mask_value')} for p in role['field_permissions'] if p['entity_type']!=ENTITY or p['field_name'] not in private]
                permissions += [dict(entity_type=ENTITY,field_name=k,can_view=False,can_edit=False,mask_value=False) for k in private]
                api.call('PUT','/roles/'+role['id'],json={'field_permissions':permissions})
                continue
            role = api.call('GET','/roles/'+summary['id'])
            if machine not in {p['machine_name'] for p in role['workflow_permissions']}: continue
            service = role['name']=='hrms_application_service'
            system = {f['field'] for f in SYSTEM_FIELDS+METADATA}
            permissions = [{k:p[k] for k in ('entity_type','field_name','can_view','can_edit','mask_value')} for p in role['field_permissions'] if p['entity_type']!=ENTITY or p['field_name'] not in fields]
            permissions += [dict(entity_type=ENTITY,field_name=k,can_view=True,can_edit=service or k not in system|EMPLOYEE_KEYS,mask_value=False) for k in fields]
            transitions = [{k:p[k] for k in ('machine_name','transition_key')} for p in role['transition_permissions']]
            granted = {(p['machine_name'],p['transition_key']) for p in transitions}
            transitions += [{'machine_name':machine,'transition_key':t['key']} for t in graph['transitions'] if (service or t['trigger'] not in EMPLOYEE_TRIGGERS) and (machine,t['key']) not in granted]
            api.call('PUT','/roles/'+role['id'],json={'field_permissions':permissions,'transition_permissions':transitions})
        db.execute('INSERT INTO hrms_feature_setup VALUES (%s,%s) ON CONFLICT DO NOTHING',(api.org,feature))


if __name__ == '__main__':
    from .platform import PlatformClient
    api=PlatformClient(os.environ['PLATFORM_API_URL'],os.environ['HRMS_ORGANIZATION_ID'],os.environ['HRMS_INSTALL_EMAIL'],os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        matches=[w for w in api.call('GET','/workflow-state-machines',params={'scope':'published'})['published_items'] if w['entity_type']==ENTITY and w['is_active']]
        if len(matches)!=1: raise AppError(409,'Expected one active offboarding workflow')
        install(api,os.environ['HRMS_APP_DATABASE_URL'],api.call('GET','/workflow-state-machines/'+matches[0]['id']))
    finally:
        api.close()
