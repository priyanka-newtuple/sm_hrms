import os
import json
import sys
import httpx
from types import SimpleNamespace
from hrms_app.platform import PlatformClient
from hrms_app.offboarding_catalog import definition, ENTITY, MACHINE
from hrms_app.offboarding import OffboardingService

api=PlatformClient(os.environ['PLATFORM_API_URL'],os.environ['HRMS_ORGANIZATION_ID'],os.environ['HRMS_INSTALL_EMAIL'],os.environ['HRMS_INSTALL_PASSWORD'])
try:
    methods={m['name']:m['method_id'] for m in api.call('GET','/method-library/methods',params={'entity_type':ENTITY,'limit':200})['items']}
    graph=definition()
    graph['entity_schema']['fields']=[]
    for state in graph['states']:
        titles=['Exit details','Exit verification']
        if state['name'] in {'Pending approval','Notice & handover','Departure confirmed','Final clearance','Completed'}:
            titles.append('Handover and clearances')
        if state['name'] in {'Final clearance','Completed'}:
            titles.append('Final HR review')
        state['method_refs']=[{'method_id':methods['Offboarding · '+t]} for t in titles]
    result=api.call('POST','/workflow-state-machines/validate',json={'machine_name':MACHINE,'definition':graph})
    print(json.dumps({'can_publish':result['can_publish'], 'issues':result['validation_report']['issues']},default=str))
    service=OffboardingService(SimpleNamespace(platform=api,journal=None))
    actor=api.actor(api.service_token())
    config=service.config(actor)
    print(json.dumps({'installed_workflow':config['workflow']['machine_name'], 'initial_fields':len(config['fields']), 'exit_records':len(service.rows(actor))}))
    if '--gateway' in sys.argv:
        for path in ('offboarding/config','offboarding','offboarding/inbox','workflows'):
            response=httpx.get('http://hrms-app:8000/v1/api/hrms/'+path,headers={'Authorization':'Bearer '+actor.token},timeout=60)
            response.raise_for_status()
            print('Gateway '+path+': OK')
finally:
    api.close()
