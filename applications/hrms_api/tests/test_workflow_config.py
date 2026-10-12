from types import SimpleNamespace
import pytest
from hrms_app.errors import AppError
from hrms_app.workflow_config import configured_workflow_rows


def test_runtime_uses_enrolled_version_and_authored_transitions_and_terminal_tags():
    calls = []
    definition = {'name':'Configured workflow','states':[
        {'name':'ready','description':'Ready for review','order':2},
        {'name':'done','description':'Finished','order':3,'tags':['terminal']},
        {'name':'new','description':'New request','order':1}],
        'transitions':[{'from':'ready','trigger':'approve','label':'Confirm approval','to_state':'done'}]}
    def call(method, path, **kw):
        calls.append(path)
        if path == '/workflow-enrollments':
            return {'items':[{'entity_id':'record','organization_id':'org','machine_name':'workflow','machine_version':2,'current_state':'ready'}], 'has_more':False}
        assert path == '/workflow-state-machines/workflow/2'
        return {'organization_id':'org','definition':definition}
    platform=SimpleNamespace(org='org',call=call)
    row=configured_workflow_rows(platform,[{'entity_id':'record','current_state':'obsolete'}])[0]
    assert row['state_label']=='Ready for review'
    assert row['is_terminal'] is False
    assert [s['name'] for s in row['workflow_configuration']['states']]==['new','ready','done']
    assert row['workflow_configuration']['transitions'][0]['label']=='Confirm approval'
    definition['states'][0]['description']='New display name'
    assert configured_workflow_rows(platform,[{'entity_id':'record'}])[0]['state_label']=='New display name'


@pytest.mark.parametrize('org',['foreign'])
def test_rejects_cross_tenant_enrollments(org):
    platform=SimpleNamespace(org='org',call=lambda *a,**k:{'items':[{'entity_id':'record','organization_id':org}], 'has_more':False})
    with pytest.raises(AppError) as error:
        configured_workflow_rows(platform,[{'entity_id':'record'}])
    assert error.value.status==502


def _platform(enrollments):
    definition = {'name': 'Leave', 'states': [{'name': 'pending'}], 'transitions': []}

    def call(method, path, **kw):
        if path == '/workflow-enrollments':
            return {'items': [dict(e, organization_id='org', machine_name='leave', machine_version=1) for e in enrollments],
                    'has_more': False}
        return {'organization_id': 'org', 'definition': definition}
    return SimpleNamespace(org='org', call=call)


BROKEN = [
    [{'entity_id': 'ok', 'current_state': 'pending'}],                                  # 'lost' has no enrollment
    [{'entity_id': 'ok', 'current_state': 'pending'}, {'entity_id': 'lost', 'current_state': 'pending'},
     {'entity_id': 'lost', 'current_state': 'pending'}],                                # 'lost' enrolled twice
    [{'entity_id': 'ok', 'current_state': 'pending'}, {'entity_id': 'lost', 'current_state': 'gone'}],  # unknown state
]


@pytest.mark.parametrize('enrollments', BROKEN)
def test_the_workflows_board_skips_only_the_broken_record(enrollments):
    rows = configured_workflow_rows(_platform(enrollments), [{'entity_id': 'ok'}, {'entity_id': 'lost'}], skip_unenrolled=True)
    assert [r['entity_id'] for r in rows] == ['ok']


@pytest.mark.parametrize('enrollments', BROKEN)
def test_other_callers_still_refuse_a_broken_record(enrollments):
    with pytest.raises(AppError) as error:
        configured_workflow_rows(_platform(enrollments), [{'entity_id': 'ok'}, {'entity_id': 'lost'}])
    assert error.value.status == 409
