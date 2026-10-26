from copy import deepcopy

import pytest

from hrms_app.errors import AppError
from hrms_app.onboarding_bindings import FORMS, initialize, resolve
from hrms_app.install_onboarding_bridge import install


class Platform:
    org = 'org'

    def __init__(self):
        self.methods = [{'name': name, 'method_id': key} for key, name in FORMS.items()]
        self.roles = []
        self.writes = []

    def call(self, method, path, **kwargs):
        if method == 'POST':
            self.writes.append(kwargs['json'])
            self.roles.append({'name': kwargs['json']['name']})
            return {}
        if path == '/method-library/methods':
            return {'organization_id': self.org, 'total': len(self.methods), 'items': deepcopy(self.methods)}
        if path == '/roles':
            return self.roles
        if path == '/workflow-state-machines':
            return {'published_items': [{'entity_type': 'HRMS.Employee', 'is_active': True, 'machine_name': 'employee', 'definition': {
                'states': [{'name': key, 'method_refs': [{'method_id': key}]} for key in FORMS],
                'method_schemas': [{'method_id': 'HRMS_EMPLOYEE_PROFILE_FORM_ID', 'fields': [{'field': 'skills'}, {'field': 'account_approved', 'read_only': True}]}],
                'transitions': [{'from': 'HRMS_EMPLOYEE_PROFILE_FORM_ID', 'key': 'submit_profile'}, {'from': 'HRMS_EMPLOYEE_APPROVAL_FORM_ID', 'key': 'approve'}],
            }}]}
        raise AssertionError(path)


@pytest.fixture(autouse=True)
def clean_bindings(monkeypatch):
    for key in FORMS:
        monkeypatch.delenv(key, raising=False)


def test_resolves_destination_ids_without_local_configuration(monkeypatch):
    platform = Platform()
    assert resolve(platform) == {key: key for key in FORMS}
    monkeypatch.setenv('HRMS_EMPLOYEE_APPROVAL_FORM_ID', 'explicit')
    platform.methods[0]['method_id'] = 'explicit'
    platform.methods[0]['name'] = 'Renamed approval form'
    assert resolve(platform)['HRMS_EMPLOYEE_APPROVAL_FORM_ID'] == 'explicit'


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'archived', 'foreign'])
def test_invalid_bindings_fail_closed(problem):
    platform = Platform()
    if problem == 'missing':
        platform.methods.pop()
    elif problem == 'duplicate':
        platform.methods.append(deepcopy(platform.methods[0]))
    elif problem == 'archived':
        platform.methods[0]['is_archived'] = True
    else:
        original = platform.call
        def foreign(*args, **kwargs):
            result = original(*args, **kwargs)
            result['organization_id'] = 'other'
            return result
        platform.call = foreign
    with pytest.raises(AppError):
        resolve(platform)


def test_only_creates_missing_role_with_profile_actions_and_no_approval_grant():
    platform = Platform()
    install(platform)
    install(platform)
    assert len(platform.writes) == 1
    role = platform.writes[0]
    assert role['transition_permissions'] == [{'machine_name': 'employee', 'transition_key': 'submit_profile'}]
    assert not next(f for f in role['field_permissions'] if f['field_name'] == 'account_approved')['can_edit']
    assert not any(p['permission_key'] in {'user:write', 'settings:access'} for p in role['permissions'])
