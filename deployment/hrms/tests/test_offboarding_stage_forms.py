import json
from pathlib import Path


def package():
    candidates = [Path('/configuration/release.json'), *(p / 'configuration/hrms/release.json' for p in Path(__file__).resolve().parents)]
    path = next(p for p in candidates if p.is_file())
    return {o['key']: o for o in json.loads(path.read_text(encoding='utf-8'))['objects']}


def fields(objects, state):
    return [f['library_field_id']['$ref'].removeprefix('field:') for ref in state['method_refs']
            for f in objects[ref['method_id']['$ref']]['payload']['fields']]


def test_each_stage_has_its_own_native_form_and_interview_has_only_notes():
    objects = package()
    graph = objects['workflow:HRMS.Offboarding']['payload']['definition']
    states = {s['name']: s for s in graph['states']}
    assert list(states) == ['Offboarding Initiated', 'Employee Checklist', 'HR Review', 'Exit Interview', 'Pending Clearance', 'Completed']
    assert fields(objects, states['Exit Interview']) == ['exit_interview_notes']
    assert 'employee_notification_email' not in fields(objects, states['Offboarding Initiated'])
    assert 'notification_email_confirmed' not in fields(objects, states['Offboarding Initiated'])
    assert {'employee_notification_email', 'notification_email_confirmed'} <= set(fields(objects, states['Employee Checklist']))
    assert 'exit_interview_completed' not in fields(objects, states['Employee Checklist'])
    assert 'exit_enjoyed' not in fields(objects, states['Employee Checklist'])
    assert 'asset_status' not in fields(objects, states['Offboarding Initiated'])
    assert 'asset_status' in fields(objects, states['Pending Clearance'])
    assert len(fields(objects, states['Offboarding Initiated'])) == 10
    for state in states.values():
        assert 'template:Exit checklist v2 · ' + state['name'] in objects
    finish = next(t for t in graph['transitions'] if t['trigger'] == 'finish_exit_interview')
    assert finish['to_state'] == 'Pending Clearance'
    assert finish['required_fields'] == [{'field': 'exit_interview_notes', 'type': 'text', 'required': True}]
    assert all(t['to_state'] == t['from'] for t in graph['transitions'] if t['trigger'] == 'confirm_departure')


def test_hr_cannot_fill_employee_contact_and_old_forms_remain_versioned():
    objects = package()
    for obj in objects.values():
        if obj['kind'] != 'role' or 'application_service' in obj['key']:
            continue
        grants = [f for f in obj['payload']['field_permissions'] if f['entity_type'] == 'HRMS.Offboarding' and f['field_name'] in {'employee_notification_email', 'notification_email_confirmed'}]
        assert grants and all(not f['can_edit'] for f in grants)
    assert 'method:Exit checklist v2 · Exit administration' in objects
