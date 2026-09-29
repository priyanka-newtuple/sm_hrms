from types import SimpleNamespace

import pytest

from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.form_config import FORM_ACCESS, form_configuration
from hrms_app.platform import Actor


def actor(role):
    return Actor('user', 'org', 'human', frozenset({role}), frozenset())


@pytest.mark.parametrize('kind', list(FORM_ACCESS))
def test_all_product_forms_use_current_native_configuration(kind):
    pack = pack_by_type(kind)
    field = {'field': 'name', 'description': 'Configured label', 'placeholder': 'Configured hint',
             'required': True, 'read_only': True, 'col_span': 2, 'type': 'string', 'default': 'not exposed'}
    form = {'schema_key': pack.schema_key, 'name': 'Configured form', 'is_active': True, 'fields': [field]}
    def call(method, path, **kwargs):
        assert (method, path, kwargs) == ('GET', '/forms/config', {'params': {'entity_type': kind}})
        return {'items': [{'schema_key': 'old_form', 'fields': []}, form]}
    api = SimpleNamespace(call=call)
    result = form_configuration(api, actor('superadmin'), kind)
    assert result['fields'][0]['description'] == 'Configured label'
    assert result['fields'][0]['required'] is True
    assert 'default' not in result['fields'][0]
    field['description'] = 'Changed after save'
    assert form_configuration(api, actor('superadmin'), kind)['fields'][0]['description'] == 'Changed after save'
    form['is_active'] = False
    with pytest.raises(AppError) as error:
        form_configuration(api, actor('superadmin'), kind)
    assert error.value.status == 409


def test_form_metadata_does_not_grant_module_or_foreign_domain_access():
    api = SimpleNamespace(call=lambda *a, **k: pytest.fail('Unauthorized upstream request'))
    for kind, role, status in [('ATS.Job', 'superadmin', 404), ('HRMS.Project', 'unconfigured_role', 403), ('HRMS.Employee', 'hrms_employee', 403)]:
        with pytest.raises(AppError) as error:
            form_configuration(api, actor(role), kind)
        assert error.value.status == status


def test_native_picklist_labels_are_resolved():
    kind = 'HRMS.LeaveRequest'
    form = {'schema_key': pack_by_type(kind).schema_key, 'name': 'Leave', 'fields': [
        {'field': 'leave_type', 'picklist_id': 'leave-kinds'}]}
    def call(method, path, **kwargs):
        return {'items': [form]} if path == '/forms/config' else {'items': [
            {'id': 'leave-kinds', 'options': [{'value': 'annual', 'label': 'Annual leave'}, 'sick']} ]}
    result = form_configuration(SimpleNamespace(call=call), actor('hrms_employee'), kind)
    assert result['fields'][0]['enum_values'] == ['annual', 'sick']
    assert result['fields'][0]['enum_labels'] == {'annual': 'Annual leave'}
