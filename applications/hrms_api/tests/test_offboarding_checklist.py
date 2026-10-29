from copy import deepcopy
import json
import pytest
from hrms_app.errors import AppError
from hrms_app.offboarding_checklist import CHECKLIST, STAGES, definition, validate_values
from test_offboarding_participation import setup


def graph():
    return definition({k:k for k in [*CHECKLIST,'Exit administration','Clearance verification']},{s:s for s in STAGES})


@pytest.fixture
def checklist(setup):
    api,actor,record,state,writes=setup
    workflow=api.context(actor,'exit')[2]
    workflow['definition']=graph()
    state.update(workflow['definition']['states'][0])
    workflow['definition']['states'][0]=state
    fields=[f for group in CHECKLIST.values() for f in group]
    api.offboarding.fields=lambda *a:fields
    record['data'].update(exit_employee_name='Employee',exit_employee_code='EMP-1',exit_date_joined='2025-01-01')
    old=api.platform.call
    def call(method,path,**kw):
        result=old(method,path,**kw)
        if method=='POST' and path.endswith('/transitions'):
            t=next(t for t in workflow['definition']['transitions'] if t['from']==state['name'] and t['trigger']==kw['json']['trigger'])
            state.update(deepcopy(next(s for s in workflow['definition']['states'] if s['name']==t['to_state'])))
        return result
    api.platform.call=call
    return api,actor,record,state,writes


def command(api,actor,key,**kwargs):
    item=api.detail(actor,'exit')
    return api.command(actor,'exit',dict(expected_hash=item['values_hash'],idempotency_key=key,**kwargs))


def answers():
    return {f['field']:('No' if f.get('enum_values') and 'No' in f['enum_values'] else True if f['type']=='boolean' else 'Response')
            for title,group in CHECKLIST.items() if title!='Employee Information' for f in group if not f['field'].endswith('_remarks')}


def test_five_native_stages_and_notification_recipients():
    d=graph()
    assert [s['name'] for s in d['states']]==STAGES
    for state in d['states']:
        mail=[a for a in state['on_state_actions'] if a['kind']=='mail.send_email']
        assert not mail
        assert state['description']=='hrms:durable-exit-notifications'
    assert not any(t['to_state']=='Completed' and t['trigger']=='submit_checklist' for t in d['transitions'])


def test_first_draft_enters_in_progress_once(checklist):
    api,actor,record,state,writes=checklist
    item=api.detail(actor,'exit')
    payload=dict(expected_hash=item['values_hash'],idempotency_key='draft',values={'exit_enjoyed':'Team'})
    api.command(actor,'exit',payload)
    api.command(actor,'exit',payload)
    assert state['name']=='In Progress'
    assert sum(method=='POST' for method,_,_ in writes)==1
    command(api,actor,'draft2',values={'exit_improvements':'Processes'})
    assert sum(method=='POST' for method,_,_ in writes)==1


def test_no_responses_can_submit_and_signature_is_server_generated(checklist):
    api,actor,record,state,writes=checklist
    command(api,actor,'draft',values=answers())
    command(api,actor,'submit',trigger='submit_checklist')
    assert state['name']=='Submitted'
    assert record['data']['checklist_submitted_by']==actor.user_id
    assert record['data']['checklist_submitted_at']
    history=json.loads(record['data']['checklist_submission_history'])
    assert len(history)==1 and history[0]['answers']['exit_assets_returned']=='No'
    assert not api.detail(actor,'exit')['editable']
    with pytest.raises(AppError,match='assigned'):
        command(api,actor,'edit-submitted',values={'exit_enjoyed':'Changed'})


def test_unanswered_or_unacknowledged_submission_rejected(checklist):
    api,actor,record,state,writes=checklist
    command(api,actor,'draft',values={'exit_assets_returned':'No'})
    with pytest.raises(AppError,match='Complete'):
        command(api,actor,'submit',trigger='submit_checklist')
    assert not record['data'].get('checklist_submitted_at')
    data=answers();data['exit_acknowledgment']=False
    command(api,actor,'draft2',values=data)
    with pytest.raises(AppError,match='Complete'):
        command(api,actor,'submit2',trigger='submit_checklist')


def test_na_only_where_configured(checklist):
    api,actor,*_=checklist
    command(api,actor,'keys',values={'exit_keys_returned':'N/A'})
    with pytest.raises(AppError):
        command(api,actor,'assets',values={'exit_assets_returned':'N/A'})


@pytest.mark.parametrize('key',['checklist_submitted_at','checklist_submitted_by','checklist_submission_history','checklist_verified','exit_employee_name'])
def test_employee_cannot_forge_metadata(checklist,key):
    api,actor,*_=checklist
    with pytest.raises(AppError,match='Only employee'):
        command(api,actor,key,values={key:'forged'})


def test_departure_can_proceed_with_documented_exception():
    d=graph()
    for state in STAGES[:2]:
        t=next(t for t in d['transitions'] if t['from']==state and t['trigger']=='confirm_departure')
        assert t['to_state']=='Pending Clearance'
        assert t['required_fields'][0]['field']=='change_reason'
        assert t['guards'][0]['field']=='departure_verified'


def test_invalid_typed_feedback_rejected():
    with pytest.raises(AppError):
        validate_values(CHECKLIST['Employee Feedback & Experience'],{'exit_enjoyed':{'unsafe':'value'}})


def test_stage_emails_use_deployment_managed_transport():
    from hrms_app.configure_email import deployment_payload
    capture = deployment_payload({'HRMS_EMAIL_MODE': 'capture'})
    assert capture['config']['smtp_host'] == 'mailpit'
    assert capture['config']['smtp_port'] == 1025
    from hrms_app.offboarding_notifications import definition as notice_definition
    for state in notice_definition()['states']:
        for action in state['on_state_actions']:
            if action['kind'] == 'mail.send_email':
                # Workflow configuration supplies content/recipients only. The
                # native default integration is selected by the release pipeline.
                assert set(action['config']) == {'to', 'template_id', 'workspace_url', 'employee_code'}
