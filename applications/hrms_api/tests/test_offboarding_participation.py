from copy import deepcopy
from types import SimpleNamespace
import pytest
from hrms_app.offboarding_participation import EmployeeOffboarding
from hrms_app.offboarding_catalog import SECTIONS
from hrms_app.errors import AppError
from hrms_app.platform import Actor
from test_offboarding import Journal


@pytest.fixture
def setup():
    actor=Actor('employee-user','org','token',frozenset({'hrms_employee'}),frozenset())
    record={'entity_id':'exit','organization_id':'org','entity_type_id':'exit-type','assignee_id':'employee-user','data':{'employee_id':'employee','identifier':'EXT-1','hr_notes':'PRIVATE','settlement_notes':'PRIVATE','exit_reason':'PRIVATE','confirmed_last_day':'2026-10-30','employee_handover_notes':'My handover'}}
    state={'name':'Employee handover','tags':[],'on_state_actions':[{'kind':'entity.assign_user','config':{'user_id':'$entity.offboarding_employee_user_id'}}]}
    workflow={'id':'workflow','organization_id':'org','entity_type':'HRMS.Offboarding','definition':{'states':[state], 'transitions':[{'from':'Employee handover','trigger':'submit_employee_handover','label':'Submit','to_state':'Notice & handover'}]}}
    writes=[]
    def call(method,path,**kw):
        if path.endswith('/with-states'):return {'entity':deepcopy(record),'states':[{'workflow_id':'workflow','current_state':state['name']}]}
        if path.startswith('/entity-types/'):return {'entity_type_id':'exit-type'}
        if path.startswith('/workflow-state-machines/'):return workflow
        writes.append((method,path,kw))
        if method=='PUT':record['data'].update(kw['json']['data'])
        return {}
    platform=SimpleNamespace(call=call,records=lambda *a:[record])
    def own(a,rows):
        return {'entity_id':'employee' if a.user_id=='employee-user' else 'someone-else'}
    service=SimpleNamespace(own_employee=own,employees=lambda:[])
    off=SimpleNamespace(platform=platform,service=service,journal=Journal(),fields=lambda *a:SECTIONS['Employee handover'])
    return EmployeeOffboarding(off),actor,record,state,writes


def test_employee_projection_never_exposes_hr_fields(setup):
    api,actor,record,state,writes=setup
    item=api.detail(actor,'exit')
    assert item['editable']
    assert not {'hr_notes','settlement_notes','exit_reason'} & item['values'].keys()
    assert 'workflow' not in item


def test_other_employee_cannot_read_exit(setup):
    api,actor,*_=setup
    other=Actor('other','org','token',frozenset(),frozenset())
    with pytest.raises(AppError,match='not available'):api.detail(other,'exit')


def test_cross_tenant_record_denied(setup):
    api,actor,record,*_=setup
    record['organization_id']='other-org'
    with pytest.raises(AppError):api.detail(actor,'exit')


def test_unassigned_employee_can_follow_but_cannot_edit(setup):
    api,actor,record,state,writes=setup
    record['assignee_id']='hr'
    item=api.detail(actor,'exit')
    assert not item['editable'] and not item['actions']
    with pytest.raises(AppError,match='assigned'):api.command(actor,'exit',{'expected_hash':item['values_hash'],'idempotency_key':'save','values':{'employee_handover_notes':'changed'}})
    assert not writes


@pytest.mark.parametrize('field',['hr_notes','departure_verified','confirmed_last_day','employee_id','offboarding_employee_user_id'])
def test_employee_cannot_change_hr_or_routing_fields(setup,field):
    api,actor,record,state,writes=setup
    item=api.detail(actor,'exit')
    with pytest.raises(AppError,match='Only employee'):api.command(actor,'exit',{'expected_hash':item['values_hash'],'idempotency_key':'save','values':{field:'changed'}})
    assert not writes


def test_draft_and_discarded_are_private(setup):
    api,actor,record,state,writes=setup
    state['tags']=['initial']
    with pytest.raises(AppError,match='not been initiated'):api.detail(actor,'exit')
    state.update(name='Discarded',tags=['terminal'])
    with pytest.raises(AppError):api.detail(actor,'exit')


def test_employee_cannot_approve_exit(setup):
    api,actor,record,state,writes=setup
    item=api.detail(actor,'exit')
    with pytest.raises(AppError,match='handover action'):api.command(actor,'exit',{'expected_hash':item['values_hash'],'idempotency_key':'approve','trigger':'approve_exit'})
    assert not writes


def test_employee_save_is_idempotent_and_preserves_hr_data(setup):
    api,actor,record,state,writes=setup
    item=api.detail(actor,'exit')
    payload={'expected_hash':item['values_hash'],'idempotency_key':'save','values':{'employee_handover_notes':'Updated'}}
    api.command(actor,'exit',payload);api.command(actor,'exit',payload)
    assert len(writes)==1
    assert record['data']['hr_notes']=='PRIVATE'
    assert record['data']['employee_handover_notes']=='Updated'
