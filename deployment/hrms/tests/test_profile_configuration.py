import json
from pathlib import Path
from hrms_app.configuration_package import validate


def test_profile_configuration_is_native_and_keeps_historical_fields():
    candidates = [Path('/configuration/release.json'), *(p / 'configuration/hrms/release.json' for p in Path(__file__).resolve().parents)]
    path = next(p for p in candidates if p.exists())
    package = json.loads(path.read_text(encoding='utf-8'))
    validate(package)
    objects = {o['key']: o['payload'] for o in package['objects']}
    assert objects['field:skills']['field_type'] == 'multi_select'
    assert len(objects['field:blood_group']['settings']['enum_values']) == 9
    fields = {f['library_field_id']['$ref'] for f in objects['method:Employee Profile Completion']['fields']}
    assert 'field:professional_experience' not in fields
    assert 'field:hr_verification_notes' not in fields
    assert 'field:professional_experience' in objects
    for key in ('emergency_contact_phone', 'permanent_same_as_current', 'marksheets', 'experience_letters', 'aadhaar_card', 'pan_card'):
        assert 'field:' + key in fields
    for transition in objects['workflow:HRMS.Employee']['definition']['transitions']:
        assert not any(f['field'] == 'hr_verification_notes' for f in transition.get('required_fields', []))


def test_account_approval_allows_service_sync_without_human_field_grants():
    candidates = [Path('/configuration/release.json'), *(p / 'configuration/hrms/release.json' for p in Path(__file__).resolve().parents)]
    package = json.loads(next(p for p in candidates if p.exists()).read_text(encoding='utf-8'))
    objects = {o['key']: o['payload'] for o in package['objects']}
    assert objects['field:account_approved']['settings'].get('read_only') is not True
    for key, payload in objects.items():
        if not key.startswith('role:'):
            continue
        grants = [g for g in payload.get('field_permissions', [])
                  if g['entity_type'] == 'HRMS.Employee' and g['field_name'] == 'account_approved']
        if key == 'role:hrms_application_service':
            assert len(grants) == 1 and grants[0]['can_edit']
        else:
            assert not any(g['can_edit'] for g in grants)
