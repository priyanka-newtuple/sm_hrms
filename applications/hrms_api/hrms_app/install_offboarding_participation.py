"""Additive native offboarding participation configuration (versioned)."""
from copy import deepcopy
import psycopg
from .offboarding_catalog import ENTITY, SECTIONS, SYSTEM_FIELDS
from .errors import AppError


def install(api, dsn, workflow):
    feature='offboarding-participation-v1'
    with psycopg.connect(dsn,autocommit=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS hrms_feature_setup (organization_id text, feature text, PRIMARY KEY (organization_id, feature))')
        if db.execute('SELECT 1 FROM hrms_feature_setup WHERE organization_id=%s AND feature=%s',(api.org,feature)).fetchone():
            return workflow
        graph=deepcopy(workflow['definition'])
        types=api.call('GET','/field-library/field-types')['items']
        routing=[f for f in SECTIONS['Exit details'] if f['field'].startswith('offboarding_') or f['field'] in {'employee_notification_email','notification_email_confirmed'}]+[f for f in SYSTEM_FIELDS if f['field']=='offboarding_employee_user_id']
        methods={}
        for title,fields in {'Offboarding routing':routing,'Employee handover':SECTIONS['Employee handover']}.items():
            links=[]
            for f in fields:
                found=next((x for x in api.call('GET','/field-library/fields',params={'search':f['field'],'limit':200})['items'] if x['identity']['field_key']==f['field']),None)
                if not found:
                    code=next(t['code'] for t in types if t['engine_type']==f['type'] and t['selectable'])
                    found=api.call('POST','/field-library/fields',json={'name':f['description'],'field_key':f['field'],'field_type':code,'settings':{k:f[k] for k in ('enum_values',) if k in f}})
                links.append({'library_field_id':found['identity']['library_field_id'],'version_id':found['version']['version_id'],'label':f['description'],'required':f.get('required',False)})
            existing=api.call('GET','/method-library/methods',params={'entity_type':ENTITY,'limit':200})['items']
            method=next((m for m in existing if m['name']=='Offboarding · '+title),None)
            if not method:
                method=api.call('POST','/method-library/methods',json={'name':'Offboarding · '+title,'entity_types':[ENTITY],'fields':links})['identity']
            methods[title]=method['method_id']
        states={s['name']:s for s in graph['states']}
        for name in ('Employee handover','Discarded'):
            if name not in states:
                s={'name':name,'order':len(states)+1,'tags':[] if name=='Employee handover' else ['terminal'],'method_refs':[],'on_state_actions':[]}
                graph['states'].append(s);states[name]=s
        for t in graph['transitions']:
            if t['trigger']=='approve_exit' and t['to_state']=='Notice & handover':
                t['to_state']='Employee handover'
            if t['trigger']=='cancel_request' and t.get('from')==graph['initial_state']:
                t['to_state']='Discarded'
        additions=[{'key':'employee_handover_submit','trigger':'submit_employee_handover','label':'Submit handover','from':'Employee handover','to_state':'Notice & handover','required_fields':[f for f in SECTIONS['Employee handover'] if f.get('required')]},
                   {'key':'employee_handover_return','trigger':'request_employee_handover','label':'Request updated employee handover','from':'Notice & handover','to_state':'Employee handover'}]
        for t in additions:
            if not any(old['key']==t['key'] for old in graph['transitions']):graph['transitions'].append(t)
        templates=api.call('GET','/email-templates')['items']
        for state in graph['states']:
            refs=state.setdefault('method_refs',[])
            if not any(r['method_id']==methods['Offboarding routing'] for r in refs):refs.append({'method_id':methods['Offboarding routing']})
            if state['name'] in {'Employee handover','Notice & handover','Final clearance','Completed'} and not any(r['method_id']==methods['Employee handover'] for r in refs):
                refs.append({'method_id':methods['Employee handover']})
            actions=state.setdefault('on_state_actions',[])
            terminal='terminal' in state.get('tags',[])
            if not terminal and not any(a['kind']=='entity.assign_user' for a in actions):
                key='offboarding_employee_user_id' if state['name']=='Employee handover' else 'offboarding_approver_id' if state['name']=='Pending approval' else 'offboarding_coordinator_id'
                config={'assignment_type':'originator'} if state['name'] in {'Draft','Changes requested'} else {'assignment_type':'user','user_id':'$entity.'+key}
                actions.insert(0,{'kind':'entity.assign_user','config':config})
            if 'initial' in state.get('tags',[]) or state['name']=='Discarded':continue
            title='MyHub offboarding · '+state['name']
            template=next((t for t in templates if t['name']==title),None)
            if not template:
                template=api.call('POST','/email-templates',json={'name':title,'entity_type':ENTITY,'subject':title,
                    'body_html':'<p>Your offboarding status is now <strong>'+state['name']+'</strong>.</p><p>While your account is active, open MyHub → My Tasks → Your offboarding to view progress and any form assigned to you. After access ends, contact HR using your agreed contact channel.</p>'})
            if not any(a['kind']=='mail.send_email' for a in actions):
                actions.append({'kind':'mail.send_email','config':{'to':'$entity.employee_notification_email','template_id':template['template_id']}})
        graph.pop('method_schemas',None)
        validation=api.call('POST','/workflow-state-machines/validate',json={'machine_name':workflow['machine_name'],'definition':graph})
        if not validation.get('can_publish'):raise AppError(422,str(validation['validation_report']))
        # A failed role update may follow a successful publish. Reuse that version
        # on retry rather than publishing an identical workflow again.
        previous=deepcopy(workflow['definition'])
        previous.pop('method_schemas',None)
        if graph == previous:
            updated=workflow
        else:
            drafts=api.call('GET','/workflow-state-machines',params={'scope':'draft','machine_name':workflow['machine_name']})['draft_items']
            draft=next(iter(drafts),None) or api.call('POST',f"/workflow-state-machines/{workflow['machine_name']}/draft")
            # Old versions/enrollments remain intact.
            updated=api.call('POST',f"/workflow-state-machines/{draft['id']}/publish",json={'definition':graph,'canvas_metadata':workflow.get('canvas_metadata')})['state_machine']
        for role in api.call('GET','/roles'):
            if role['name'] not in {'superadmin','hrms_hr_full','hrms_application_service'}:continue
            r=api.call('GET',f"/roles/{role['id']}")
            # Existing human workflow revocations must survive feature upgrades.
            if updated['machine_name'] not in {p['machine_name'] for p in r['workflow_permissions']}:
                if role['name']=='hrms_application_service':
                    raise AppError(409, 'Install base offboarding workflow access before participation permissions')
                continue
            fieldkeys={f['field'] for f in routing+SECTIONS['Employee handover']}
            fields=[{k:p[k] for k in ('entity_type','field_name','can_view','can_edit','mask_value')} for p in r['field_permissions'] if p['entity_type']!=ENTITY or p['field_name'] not in fieldkeys]
            fields += [dict(entity_type=ENTITY,field_name=k,can_view=True,can_edit=role['name']=='hrms_application_service' or k not in {'offboarding_employee_user_id',*[f['field'] for f in SECTIONS['Employee handover']]},mask_value=False) for k in fieldkeys]
            transitions=[{k:p[k] for k in ('machine_name','transition_key')} for p in r['transition_permissions']]
            existing={(p['machine_name'],p['transition_key']) for p in transitions}
            for t in additions:
                if t['trigger']=='submit_employee_handover' and role['name']!='hrms_application_service':continue
                if (updated['machine_name'],t['key']) not in existing:transitions.append({'machine_name':updated['machine_name'],'transition_key':t['key']})
            api.call('PUT',f"/roles/{role['id']}",json={'field_permissions':fields,'transition_permissions':transitions})
        db.execute('INSERT INTO hrms_feature_setup VALUES (%s,%s) ON CONFLICT DO NOTHING',(api.org,feature))
        return updated
