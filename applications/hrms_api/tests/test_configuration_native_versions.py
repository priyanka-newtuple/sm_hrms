"""Contract-shaped fake native API exercises repinning across environment IDs."""
from copy import deepcopy

from hrms_app.configuration_native import NativeConfiguration
from hrms_app.configuration_package import make_plan
from hrms_app.configuration_promotion import apply, inspection
from test_configuration_promotion import MemoryJournal


class NativeAPI:
    org = 'destination'

    def __init__(self):
        self.writes = []
        self.field = {'identity': {'library_field_id': 'field-dest', 'field_key': 'name', 'name': 'Name'},
                      'version': {'version_id': 'field-version-1', 'field_type': 'TEXT',
                                  'description': None, 'settings': {'hint': 'old'}}}
        self.method = {'identity': {'method_id': 'method-dest', 'name': 'Employee details',
                                    'description': None, 'category_id': None, 'entity_types': ['Employee']},
                       'version': {'version_id': 'method-version-1', 'connector_id': None},
                       'fields': [{'library_field_id': 'field-dest', 'field_version_id': 'field-version-1',
                                   'label': 'Name', 'position': 0, 'required': True}]}
        self.workflow = {'id': 'workflow-row-1', 'machine_name': 'workflow-dest', 'entity_type': 'Employee',
                         'is_active': True, 'canvas_metadata': None, 'definition': {
                             'machine_key': 'workflow-dest', 'name': 'Add Employee', 'entity_type': 'Employee',
                             'states': [{'name': 'Draft', 'method_refs': [{'method_id': 'method-dest',
                                                                         'version_id': 'method-version-1'}]}]}}
        self.enrollment = {'entity_id': 'employee-existing', 'machine_version': 1}

    def call(self, verb, route, **kwargs):
        if verb != 'GET':
            self.writes.append((verb, route))
        if route == '/field-library/fields':
            return {'items': [deepcopy(self.field)], 'total': 1}
        if route == '/method-library/methods':
            return {'items': [deepcopy(self.method['identity'])], 'total': 1}
        if route == '/method-library/methods/method-dest':
            return deepcopy(self.method)
        if route == '/workflow-state-machines':
            if kwargs['params']['scope'] == 'draft':
                return {'draft_items': []}
            return {'published_items': [deepcopy(self.workflow)]}
        if verb == 'GET' and route.startswith('/workflow-state-machines/workflow-row-'):
            return deepcopy(self.workflow)
        if route == '/field-library/fields/field-dest/versions':
            self.field['version'] = {**deepcopy(kwargs['json']), 'version_id': 'field-version-2'}
            return deepcopy(self.field['version'])
        if route == '/method-library/methods/method-dest/fields':
            self.method['fields'] = []
            for field in kwargs['json']['fields']:
                field = deepcopy(field)
                field['field_version_id'] = field.pop('version_id')
                self.method['fields'].append(field)
            self.method['version']['version_id'] = 'method-version-2'
            return deepcopy(self.method)
        if route == '/workflow-state-machines/validate':
            return {'can_publish': True}
        if route == '/workflow-state-machines/workflow-dest/draft':
            return {'id': 'draft-owned', 'machine_name': 'workflow-dest'}
        if route == '/workflow-state-machines/draft-owned/publish':
            self.workflow.update(deepcopy(kwargs['json']))
            self.workflow['id'] = 'workflow-row-2'
            return {'state_machine': deepcopy(self.workflow)}
        raise AssertionError((verb, route))


def test_workflow_snapshot_excludes_native_generated_field_projection():
    api = NativeAPI()
    api.workflow['definition']['entity_schema'] = {'entity_type': 'Employee', 'fields': [
        {'field': 'manual', 'source_states': []},
        {'field': 'name', 'source_states': ['Draft'], 'enum_values': ['stale']}]}
    payload, _ = NativeConfiguration(api).read({'kind': 'workflow', 'match': 'Employee'})
    assert payload['definition']['entity_schema']['fields'] == [{'field': 'manual', 'source_states': []}]


def test_changed_field_repins_method_and_workflow_without_touching_enrollment():
    api = NativeAPI()
    native = NativeConfiguration(api)
    specs = [{'kind': kind, 'key': key, 'match': match, 'payload': {}}
             for kind, key, match in [('field', 'field:name', 'name'),
                                      ('method', 'method:details', 'Employee details'),
                                      ('workflow', 'workflow:Employee', 'Employee')]]
    baseline, _ = native.snapshot(specs)
    desired = deepcopy(baseline)
    desired['field:name']['payload']['settings']['hint'] = 'new'
    package = {'schema_version': 1, 'name': 'hrms-test', 'objects': list(desired.values())}
    journal = MemoryJournal({'baseline': baseline, 'status': 'applied'})
    plan, _, _ = inspection(native, package, journal.read())
    apply(native, package, plan, journal)
    assert api.method['fields'][0]['field_version_id'] == 'field-version-2'
    assert api.workflow['definition']['states'][0]['method_refs'][0]['version_id'] == 'method-version-2'
    assert api.enrollment == {'entity_id': 'employee-existing', 'machine_version': 1}
    assert ('POST', '/workflow-state-machines/draft-owned/publish') in api.writes
    writes = deepcopy(api.writes)
    plan, _, _ = inspection(native, package, journal.read())
    apply(native, package, plan, journal)
    assert api.writes == writes


def test_only_serialization_equivalent_draft_can_be_reused():
    import pytest
    from hrms_app.configuration_package import ConfigurationError
    api=NativeAPI()
    api.workflow['definition']['transitions']=[{'key':'next','from':'Draft','to_state':'Done'}]
    draft=deepcopy(api.workflow);draft['id']='existing-draft'
    draft['definition']['transitions'][0]['from_state']=draft['definition']['transitions'][0].pop('from')
    original=api.call
    def call(verb,route,**kw):
        if route=='/workflow-state-machines' and kw['params']['scope']=='draft':return {'draft_items':[{'id':'existing-draft'}]}
        if route=='/workflow-state-machines/existing-draft':return deepcopy(draft)
        return original(verb,route,**kw)
    api.call=call
    native=NativeConfiguration(api)
    identity={'id':'workflow-row-1','machine_name':'workflow-dest'}
    assert native.reusable_workflow_draft(identity)['id']=='existing-draft'
    draft['definition']['transitions'][0]['to_state']='Different'
    with pytest.raises(ConfigurationError,match='Edited workflow draft'):native.reusable_workflow_draft(identity)
    assert not api.writes
