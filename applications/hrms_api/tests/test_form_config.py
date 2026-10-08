from types import SimpleNamespace

import pytest

from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.form_config import FORM_ACCESS, configured_form, form_configuration, has_method_blocks
from hrms_app.platform import Actor
from test_performance import UNMIGRATED_TENANT


def actor(role):
    return Actor('user', 'org', 'human', frozenset({role}), frozenset())


def platform(**routes):
    """A platform answering GETs from `routes`, otherwise as a tenant not on method blocks."""
    calls = []

    def call(method, path, **kwargs):
        assert method == 'GET', (method, path)
        calls.append(path)
        answer = routes.get(path, UNMIGRATED_TENANT.get(path))
        assert answer is not None, f'Unexpected request {path}'
        return answer(kwargs) if callable(answer) else answer

    return SimpleNamespace(call=call, calls=calls)


def workflow(kind, fields, pinned=True):
    states = [{'name': 'draft', 'method_refs': [{'method_id': 'm1'}] if pinned else []}]
    return {'published_items': [
        {'entity_type': kind, 'is_active': False, 'name': 'Old', 'definition': {'states': states, 'entity_schema': {'fields': []}}},
        {'entity_type': kind, 'is_active': True, 'name': 'Policy', 'definition': {'states': states, 'entity_schema': {'fields': fields}}},
    ]}


@pytest.mark.parametrize('kind', list(FORM_ACCESS))
def test_unmigrated_forms_use_current_native_configuration(kind):
    pack = pack_by_type(kind)
    field = {'field': 'name', 'description': 'Configured label', 'placeholder': 'Configured hint',
             'required': True, 'read_only': True, 'col_span': 2, 'type': 'string', 'default': 'not exposed'}
    form = {'schema_key': pack.schema_key, 'name': 'Configured form', 'is_active': True, 'fields': [field]}

    def forms(kwargs):
        assert kwargs == {'params': {'entity_type': kind}}
        return {'items': [{'schema_key': 'old_form', 'fields': []}, form]}

    api = platform(**{'/forms/config': forms})
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
    api = platform(**{'/forms/config': {'items': [form]}, '/config/picklists': {'items': [
        {'id': 'leave-kinds', 'options': [{'value': 'annual', 'label': 'Annual leave'}, 'sick']}]}})
    result = form_configuration(api, actor('hrms_employee'), kind)
    assert result['fields'][0]['enum_values'] == ['annual', 'sick']
    assert result['fields'][0]['enum_labels'] == {'annual': 'Annual leave'}


def test_a_migrated_type_follows_its_active_workflow_not_the_legacy_form():
    fields = [{'field': 'approver_id', 'type': 'phone', 'description': 'Approver', 'required': False,
               'placeholder': 'Pick one', 'editable': False, 'source_states': ['draft']}]
    api = platform(**{'/workflow-state-machines': workflow('HRMS.Policy', fields)})

    result = configured_form(api, 'HRMS.Policy')

    assert result['name'] == 'Policy'
    assert result['fields'] == [{'field': 'approver_id', 'description': 'Approver', 'placeholder': 'Pick one',
                                 'required': False, 'read_only': True, 'col_span': None, 'type': 'phone',
                                 'enum_values': None}]
    assert '/forms/config' not in api.calls
    fields[0]['description'] = 'Changed in Settings'
    assert configured_form(api, 'HRMS.Policy')['fields'][0]['description'] == 'Changed in Settings'


def test_a_workflow_without_pinned_blocks_keeps_the_legacy_form():
    form = {'schema_key': pack_by_type('HRMS.Policy').schema_key, 'name': 'Legacy', 'fields': [{'field': 'title', 'type': 'string'}]}
    blocks = {'items': [{'method_id': 'unpinned', 'name': 'Draft block', 'method_code': 1}]}
    api = platform(**{'/workflow-state-machines': workflow('HRMS.Policy', [{'field': 'title', 'type': 'text'}], pinned=False),
                      '/forms/config': {'items': [form]}, '/method-library/methods': blocks})

    result = configured_form(api, 'HRMS.Policy')

    assert result['name'] == 'Legacy' and result['fields'][0]['type'] == 'string'
    assert '/method-library/methods' not in api.calls


def test_a_type_without_a_workflow_follows_its_method_blocks():
    blocks = {'items': [{'method_id': 'b2', 'name': 'Second', 'method_code': 2},
                        {'method_id': 'b1', 'name': 'Customer form', 'method_code': 1}]}
    details = {
        '/method-library/methods/b1': {'fields': [
            {'field_key': 'contract_value', 'field_type': 'decimal', 'label': 'Contract value', 'required': True, 'position': 1},
            {'field_key': 'name', 'field_type': 'text', 'label': 'Customer name', 'position': 0,
             'settings': {'col_span': 2, 'read_only': True}},
        ]},
        '/method-library/methods/b2': {'fields': [{'field_key': 'name', 'field_type': 'textarea', 'label': 'Ignored', 'position': 0}]},
    }
    types = {'items': [{'code': 'text', 'engine_type': 'string'}, {'code': 'decimal', 'engine_type': 'float'}]}
    api = platform(**{'/method-library/methods': blocks, '/field-library/field-types': types, **details})

    result = configured_form(api, 'HRMS.Customer')

    assert [(f['field'], f['type'], f['description']) for f in result['fields']] == [
        ('name', 'string', 'Customer name'), ('contract_value', 'float', 'Contract value')]
    assert result['fields'][0]['read_only'] is True and result['fields'][0]['col_span'] == 2
    assert result['fields'][1]['required'] is True
    assert '/forms/config' not in api.calls


def test_pinned_select_values_get_their_picklist_labels_back():
    fields = [{'field': 'project_role_id', 'type': 'enum', 'enum_values': ['r2', 'r1']},
              {'field': 'leave_type', 'type': 'enum', 'enum_values': ['annual']}]
    # A role added to the picklist after the workflow was published must not drop the labels.
    picklists = {'items': [{'id': 'roles', 'options': [{'value': 'r1', 'label': 'Engineer'}, {'value': 'r2', 'label': 'Designer'},
                                                       {'value': 'r3', 'label': 'Added later'}]}]}
    api = platform(**{'/workflow-state-machines': workflow('HRMS.Allocation', fields), '/config/picklists': picklists})

    role, leave = configured_form(api, 'HRMS.Allocation')['fields']

    assert role['enum_values'] == ['r2', 'r1']
    assert role['enum_labels'] == {'r1': 'Engineer', 'r2': 'Designer'}
    assert leave['enum_values'] == ['annual'] and 'enum_labels' not in leave


def test_two_active_workflows_are_refused():
    published = workflow('HRMS.Policy', [])
    published['published_items'][0]['is_active'] = True
    with pytest.raises(AppError) as error:
        configured_form(platform(**{'/workflow-state-machines': published}), 'HRMS.Policy')
    assert error.value.status == 409


def test_method_blocks_mark_a_type_as_migrated():
    assert has_method_blocks(platform(**{'/method-library/methods': {'items': [{'method_id': 'm'}]}}), 'HRMS.Policy')
    assert not has_method_blocks(platform(), 'HRMS.Policy')


def test_labels_generated_by_the_migration_leave_the_screen_wording():
    fields = [{'field': 'pm_name', 'type': 'string', 'description': 'Pm Name'},
              {'field': 'start_date', 'type': 'datetime', 'description': 'Kick-off'}]
    api = platform(**{'/workflow-state-machines': workflow('HRMS.Project', fields)})

    generated, chosen = configured_form(api, 'HRMS.Project')['fields']

    assert generated['description'] is None
    assert chosen['description'] == 'Kick-off'
