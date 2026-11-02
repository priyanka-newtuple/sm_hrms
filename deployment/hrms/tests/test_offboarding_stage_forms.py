import json
from pathlib import Path


def package():
    candidates = [Path('/configuration/release.json'), *(p / 'configuration/hrms/release.json' for p in Path(__file__).resolve().parents)]
    path = next(p for p in candidates if p.is_file())
    return {o['key']: o for o in json.loads(path.read_text(encoding='utf-8'))['objects']}


def fields(objects, state):
    return [f['library_field_id']['$ref'].removeprefix('field:') for ref in state['method_refs']
            for f in objects[ref['method_id']['$ref']]['payload']['fields']]


def test_release_library_fields_have_unique_native_names_and_explicit_defaults():
    objects = package()
    names = set()
    for obj in objects.values():
        if obj['kind'] != 'field':
            continue
        payload = obj['payload']
        identity = (payload['name'].lower(), payload['field_type'])
        assert identity not in names, obj['key']
        names.add(identity)
        assert 'description' in payload
    for obj in objects.values():
        if obj['kind'] == 'method':
            assert {'description', 'category_id'} <= obj['payload'].keys()
            for field in obj['payload']['fields']:
                assert {'placeholder', 'ownership', 'inherit_from', 'source_entity_type', 'source_field_key'} <= field.keys()


def test_simplified_stages_use_separate_native_forms():
    objects = package()
    graph = objects['workflow:HRMS.Offboarding']['payload']['definition']
    states = {s['name']: s for s in graph['states']}
    assert list(states) == ['Start offboarding', 'Employee checklist', 'Project Manager Clearance', 'Asset and Subscriptions Clearance', 'Exit interview', 'HRMS Access Removal', 'Awaiting HR completion', 'Completed']
    expected = {
        'Start offboarding': {'employee_id', 'exit_type', 'confirmed_last_day', 'exit_reason', 'supporting_documents', 'offboarding_project_manager_id', 'offboarding_office_admin_id'},
        'Employee checklist': {'employee_notification_email', 'exit_projects_handed_over', 'exit_tasks_updated'},
        'Project Manager Clearance': {'project_release_approved', 'project_clearance_comments'},
        'Asset and Subscriptions Clearance': {'clearance_assets_received', 'clearance_licenses_revoked', 'asset_clearance_comments'},
        'Exit interview': {'exit_interview_done', 'exit_employee_feedback', 'exit_interview_date', 'offboarding_access_admin_id'},
    }
    for name, keys in expected.items():
        assert set(fields(objects, states[name])) == keys
    for name in states:
        assert 'template:Exit checklist v2 · ' + name in objects
    assert not any(t['trigger'] == 'confirm_departure' for t in graph['transitions'])
    assert 'method:Exit checklist v2 · Exit administration' in objects


def test_all_human_roles_can_submit_their_own_checklist():
    objects = package()
    for obj in objects.values():
        if obj['kind'] != 'role' or 'application_service' in obj['key']:
            continue
        role = obj['payload']
        assert any(t['transition_key'] == 'v4_submit_checklist_1' for t in role['transition_permissions'])
        for key in ('employee_notification_email', 'exit_projects_handed_over', 'exit_tasks_updated'):
            assert any(f['entity_type'] == 'HRMS.Offboarding' and f['field_name'] == key and f['can_view'] and f['can_edit'] for f in role['field_permissions'])


def test_native_transition_fields_resolve_in_the_source_stage():
    objects = package()
    graph = objects['workflow:HRMS.Offboarding']['payload']['definition']
    global_fields = {f['field'] for f in graph['entity_schema']['fields'] if not f.get('source_states')}
    states = {s['name']: set(fields(objects, s)) | global_fields for s in graph['states']}
    for transition in graph['transitions']:
        referenced = {f['field'] for f in transition['required_fields']}
        referenced |= {g['field'] for g in transition['guards'] if g.get('field')}
        assert referenced <= states[transition['from']], (transition['key'], referenced - states[transition['from']])
    assert global_fields == {'checklist_verified', 'departure_verified', 'clearance_verified'}


def test_access_removal_is_last_admin_action_then_hr_completion():
    objects = package()
    graph = objects['workflow:HRMS.Offboarding']['payload']['definition']
    transitions = {t['trigger']:t for t in graph['transitions']}
    assert transitions['send_access_removal']['to_state'] == 'HRMS Access Removal'
    assert transitions['disable_hrms_access']['from'] == 'HRMS Access Removal'
    assert transitions['disable_hrms_access']['to_state'] == 'Awaiting HR completion'
    assert transitions['complete_offboarding']['from'] == 'Awaiting HR completion'
    assert transitions['complete_offboarding']['to_state'] == 'Completed'
    for name, expected in [('superadmin',True),('hrms_hr_full',False),('hrms_office_admin',False),('hrms_employee',False)]:
        permissions = objects['role:'+name]['payload']['transition_permissions']
        assert any(p['transition_key']=='v4_disable_hrms_access_5' for p in permissions) == expected
    assert any(p['transition_key']=='v4_complete_offboarding_6' for p in objects['role:hrms_hr_full']['payload']['transition_permissions'])
    states = {s['name']:s for s in graph['states']}
    assert states['HRMS Access Removal']['on_state_actions'][0]['config']['user_id'] == '$entity.offboarding_access_admin_id'
    assert states['Awaiting HR completion']['on_state_actions'][0]['config']['user_id'] == '$entity.offboarding_coordinator_id'
    assert 'terminal' not in states['Awaiting HR completion']['tags']
