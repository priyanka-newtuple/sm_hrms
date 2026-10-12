"""Fields an organization adds in Settings show up, are checked and are saved on HRMS screens."""
import pytest

from hrms_app import custom_fields
from hrms_app.errors import AppError
from test_employees import StaffPlatform, hr, service, update

pytestmark = pytest.mark.custom_fields
CONFIGURED = [
    {'field': 'blood_group', 'type': 'enum', 'enum_values': ['A+', 'B+', 'O+'], 'required': True, 'description': 'Blood group'},
    {'field': 'shirt_size', 'type': 'string'},
    {'field': 'years_experience', 'type': 'integer'},
    {'field': 'ctc_lakhs', 'type': 'decimal'},
    {'field': 'relocating', 'type': 'boolean'},
    {'field': 'visa_expiry', 'type': 'date'},
    {'field': 'badge_number', 'type': 'string', 'read_only': True},
]


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(custom_fields, 'custom_fields', lambda platform, entity_type: CONFIGURED)


def check(values, current=None):
    return custom_fields.check_custom(None, 'HRMS.Employee', values, current)


def test_values_are_checked_against_their_configured_type():
    saved = check({'blood_group': 'O+', 'years_experience': 4, 'ctc_lakhs': 12, 'relocating': False, 'visa_expiry': '2027-05-01'})
    assert saved == {'blood_group': 'O+', 'years_experience': 4, 'ctc_lakhs': 12.0, 'relocating': False, 'visa_expiry': '2027-05-01'}


@pytest.mark.parametrize(('values', 'message'), [
    ({}, 'Blood group is required'),
    ({'blood_group': 'Z'}, 'configured options'),
    ({'blood_group': 'A+', 'years_experience': 2.5}, 'whole number'),
    ({'blood_group': 'A+', 'relocating': 'yes'}, 'yes or no'),
    ({'blood_group': 'A+', 'visa_expiry': 'soon'}, 'must be a date'),
    ({'blood_group': 'A+', 'salary': 1}, 'Not on the configured form: salary'),
])
def test_wrong_values_are_refused(values, message):
    with pytest.raises(AppError, match=message) as error:
        check(values)
    assert error.value.status == 422


def test_editing_keeps_saved_values_and_read_only_fields():
    current = {'blood_group': 'B+', 'shirt_size': 'M', 'badge_number': 'B-17'}
    assert check({'shirt_size': 'L', 'badge_number': 'hacked'}, current) == {'blood_group': 'B+', 'shirt_size': 'L', 'badge_number': 'B-17'}


def test_a_custom_field_is_saved_with_the_employee_and_returned():
    platform = StaffPlatform()
    result = service(platform).update_employee(hr(), 'dev', update(custom={'blood_group': 'A+', 'shirt_size': 'XL'}))
    assert platform.rows['dev']['data']['blood_group'] == 'A+'
    assert result['custom'] == {'blood_group': 'A+', 'shirt_size': 'XL'}


def test_the_service_role_is_granted_new_fields_without_losing_any(monkeypatch):
    from hrms_app import field_access
    monkeypatch.setattr(field_access, 'configured_fields',
                        lambda platform, kind: ['first_name', 'blood_group'] if kind == 'HRMS.Employee' else [])
    role = {'field_permissions': [dict(id='1', entity_type='HRMS.Employee', field_name='first_name', can_view=True, can_edit=True, mask_value=False)]}
    calls = []

    def call(method, path, json=None):
        calls.append((method, path, json))
        return [{'id': 'svc', 'name': 'hrms_application_service'}] if path == 'roles' else role
    added = field_access.sync_service_field_access(None, call)
    assert added == [field_access.grant('HRMS.Employee', 'blood_group')]
    assert [f['field_name'] for f in calls[-1][2]['field_permissions']] == ['first_name', 'blood_group']
    assert field_access.changes_forms('PUT', 'method-library/methods/m1/fields')
    assert not field_access.changes_forms('GET', 'method-library/methods') and not field_access.changes_forms('PUT', 'roles/r1')


def test_requests_without_custom_fields_match_retries_from_before_they_existed():
    from hrms_app.requests import LeaveCreateRequest
    from hrms_app.service import fingerprint
    request = dict(start_date='2041-01-07', end_date='2041-01-07', leave_type='casual', idempotency_key='retry-key-1')
    assert 'custom' not in fingerprint(LeaveCreateRequest(**request))
    assert fingerprint(LeaveCreateRequest(**request, custom={'blood_group': 'A+'}))['custom'] == {'blood_group': 'A+'}
