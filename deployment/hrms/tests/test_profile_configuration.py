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
