from copy import deepcopy
from types import SimpleNamespace

import pytest

from hrms_app.configuration_package import (ConfigurationError, digest, make_plan, portable,
                                            reference, resolve, validate, verify_plan)
from hrms_app.configuration_promotion import adopt_reviewed, apply, inspection, reconcile
from hrms_app.configuration_native import NativeConfiguration


def obj(name='Departments', **extra):
    return {'key': name, 'kind': 'picklist', 'match': name,
            'payload': {'name': name, 'options': extra.get('options', [])}}


def package(*objects):
    return {'schema_version': 1, 'name': 'test-release', 'objects': list(objects or [obj()])}


class MemoryJournal:
    def __init__(self, state=None):
        self.state = deepcopy(state or {'baseline': {}, 'status': 'not_applied'})
        self.writes = []

    def read(self):
        return deepcopy(self.state)

    def save(self, state):
        self.state = deepcopy(state)
        self.writes.append(deepcopy(state))


class FakeNative:
    def __init__(self, rows=None):
        self.api = SimpleNamespace(org='tenant-a')
        self.rows = deepcopy(rows or {})
        self.writes = []
        self.fail = False

    def snapshot(self, objects):
        return deepcopy(self.rows), {k: {'id': k} for k in self.rows}

    def read(self, item):
        row = self.rows.get(item['key'])
        return (deepcopy(row['payload']), {'id': item['key']}) if row else (None, {})

    def preflight(self, objects, identities):
        pass

    def write(self, item, payload, identity, checkpoint):
        self.writes.append(item['key'])
        self.rows[item['key']] = deepcopy(item)
        if self.fail:
            raise TimeoutError('Response lost after successful native write')


@pytest.mark.parametrize('before,current,desired,decision', [
    (None, None, obj(), 'create'),
    (None, obj(), obj(), 'adopt'),
    (obj(), obj(), obj(), 'unchanged'),
    (obj(), obj(), obj(options=[{'value': 'HR', 'label': 'HR'}]), 'update'),
    (None, obj(options=['manual']), obj(), 'conflict'),
    (obj(), None, obj(), 'conflict'),
    (obj(), obj(options=['manual']), obj(), 'conflict'),
    (obj(), obj(), None, 'retirement_required'),
])
def test_three_way(before, current, desired, decision):
    # Keep a second object so testing removal still uses a nonempty package.
    p = package(obj('Other'), *([desired] if desired else []))
    plan = make_plan(p, {'Departments': current} if current else {},
                     {'Departments': before} if before else {}, 'tenant-a')
    assert next(x for x in plan['operations'] if x['key'] == 'Departments')['decision'] == decision


@pytest.mark.parametrize('value', [
    {'password': 'never-export'}, {'organization_id': 'other'}, {'user_id': 'employee-1'},
    {'template_id': '00000000-0000-0000-0000-000000000001'},
    {'to': 'employee@example.com'}, {'endpoint': 'https://example.com'},
    {'connector_id': 'secret-connection'},
])
def test_environment_values_rejected(value):
    with pytest.raises(ConfigurationError):
        portable(value)


def test_dynamic_native_assignment_is_configuration_not_a_user():
    portable({'user_id': '$entity.offboarding_approver_id'})
    with pytest.raises(ConfigurationError):
        portable({'password': '$entity.password'})


def test_references_order_and_unknown_or_cycle():
    child = obj('Child')
    child['payload']['options'] = [reference('Parent')]
    assert [o['key'] for o in validate(package(child, obj('Parent')))] == ['Parent', 'Child']
    with pytest.raises(ConfigurationError, match='Unresolved'):
        validate(package(child))
    parent = obj('Parent', options=[reference('Child')])
    with pytest.raises(ConfigurationError, match='cycle'):
        validate(package(child, parent))
    assert resolve(reference('Parent'), {'Parent': {'id': 'destination'}}) == 'destination'


def test_package_cannot_replay_arbitrary_api_or_records():
    bad = obj()
    bad['kind'] = 'entity_record'
    with pytest.raises(ConfigurationError):
        validate(package(bad))
    bad = obj()
    bad['payload']['endpoint'] = '/entity-records'
    with pytest.raises(ConfigurationError):
        validate(package(bad))


def test_stale_tenant_or_snapshot_plan_refused():
    plan = make_plan(package(), {}, {}, 'tenant-a')
    for fresh in [make_plan(package(), {}, {}, 'tenant-b'),
                  make_plan(package(), {'Departments': obj()}, {}, 'tenant-a')]:
        with pytest.raises(ConfigurationError):
            verify_plan(plan, fresh)


def test_apply_verifies_and_noop_does_not_write():
    native, journal, p = FakeNative(), MemoryJournal(), package()
    plan, _, _ = inspection(native, p, journal.read())
    result = apply(native, p, plan, journal)
    assert result['status'] == 'applied'
    assert native.writes == ['Departments']
    plan, _, _ = inspection(native, p, journal.read())
    apply(native, p, plan, journal)
    assert native.writes == ['Departments']


def test_conflict_never_writes():
    native = FakeNative({'Departments': obj(options=['production'])})
    journal = MemoryJournal()
    plan, _, _ = inspection(native, package(), journal.read())
    with pytest.raises(ConfigurationError):
        apply(native, package(), plan, journal)
    assert not native.writes
    assert not journal.writes


def test_reviewed_adoption_preserves_before_values_and_uses_verified_apply():
    before = obj(options=['production'])
    native, journal = FakeNative({'Departments': before}), MemoryJournal()
    plan, _, _ = inspection(native, package(), journal.read())
    result = adopt_reviewed(native, package(), plan, journal)
    assert result['status'] == 'applied'
    assert journal.writes[0]['baseline']['Departments'] == before
    assert journal.writes[0]['adoption_review'] == plan
    assert native.writes == ['Departments']


def test_reviewed_adoption_rejects_drift_and_already_managed_packages():
    native, journal = FakeNative({'Departments': obj(options=['production'])}), MemoryJournal()
    plan, _, _ = inspection(native, package(), journal.read())
    native.rows['Departments'] = obj(options=['new edit'])
    with pytest.raises(ConfigurationError, match='stale'):
        adopt_reviewed(native, package(), plan, journal)
    assert not native.writes and not journal.writes
    journal.state['status'] = 'failed'
    with pytest.raises(ConfigurationError, match='unmanaged'):
        adopt_reviewed(native, package(), plan, journal)


def test_reviewed_adoption_preflight_failure_has_no_writes():
    native, journal = FakeNative(), MemoryJournal()
    plan, _, _ = inspection(native, package(), journal.read())
    def reject(*args):
        raise ConfigurationError('Unsupported migration')
    native.preflight = reject
    with pytest.raises(ConfigurationError, match='Unsupported'):
        adopt_reviewed(native, package(), plan, journal)
    assert not native.writes and not journal.writes


def test_lost_response_requires_verified_reconciliation_not_duplicate_write():
    native, journal, p = FakeNative(), MemoryJournal(), package()
    native.fail = True
    plan, _, _ = inspection(native, p, journal.read())
    with pytest.raises(TimeoutError):
        apply(native, p, plan, journal)
    assert journal.state['status'] == 'failed'
    assert journal.state['pending']['key'] == 'Departments'
    assert journal.writes[1]['pending']['key'] == 'Departments'
    with pytest.raises(ConfigurationError, match='incomplete'):
        apply(native, p, plan, journal)
    assert reconcile(native, p, journal)['status'] == 'applied'
    assert native.writes == ['Departments']


def test_partial_release_cannot_be_marked_reconciled():
    p = package(obj(), obj('Second'))
    journal = MemoryJournal({'status': 'failed', 'package_checksum': digest(p), 'baseline': {}})
    with pytest.raises(ConfigurationError, match='partial'):
        reconcile(FakeNative({'Departments': obj()}), p, journal)


def test_native_api_tenant_scope_and_incomplete_pages():
    api = SimpleNamespace(org='tenant-a', call=lambda *a, **k: {'organization_id': 'other', 'items': []})
    with pytest.raises(ConfigurationError, match='tenant'):
        NativeConfiguration(api).listing('/config/picklists')
    api.call = lambda *a, **k: {'items': [], 'total': 1}
    with pytest.raises(ConfigurationError, match='pagination'):
        NativeConfiguration(api).listing('/method-library/methods', paged=True)


def test_native_write_only_targets_configuration():
    calls = []
    api = SimpleNamespace(org='tenant-a', call=lambda *a, **k: calls.append((a, k)))
    native = NativeConfiguration(api)
    native.write(obj(), obj()['payload'], {}, lambda _: None)
    assert calls[0][0] == ('POST', '/config/picklists')


def test_human_draft_blocked_before_writes():
    native = NativeConfiguration(SimpleNamespace(org='tenant-a'))
    item = {'key': 'wf', 'kind': 'workflow', 'match': 'Employee', 'payload': {'definition': {'name': 'changed'}}}
    native.read = lambda o: ({'definition': {}}, {'id': 'row', 'machine_name': 'family'})
    native.get = lambda *a, **k: {'draft_items': [{'id': 'human-draft'}]}
    with pytest.raises(ConfigurationError, match='draft'):
        native.preflight([item], {'wf': {'id': 'row', 'machine_name': 'family'}})


def test_role_scope_cannot_grant_unrelated_entities():
    role = {'key': 'role:hr', 'kind': 'role', 'match': 'hr', 'payload': {
        'entity_scope': ['Employee'], 'workflow_scope': [reference('workflow:Employee', 'machine_name')],
        'entity_permissions': [{'entity_type': 'Payroll', 'action': 'view'}]}}
    entity = {'key': 'entity:Employee', 'kind': 'entity', 'match': 'Employee', 'payload': {'name': 'Employee'}}
    wf = {'key': 'workflow:Employee', 'kind': 'workflow', 'match': 'Employee', 'payload': {'definition': {}}}
    with pytest.raises(ConfigurationError, match='outside'):
        validate(package(entity, wf, role))


def test_role_updates_preserve_unrelated_grants_and_grant_access_first():
    calls = []
    current = {'id': 'role-id', 'workflow_permissions': [{'machine_name': 'projects'}],
               'transition_permissions': [{'machine_name': 'projects', 'transition_key': 'approve'}],
               'entity_permissions': [{'entity_type': 'Project', 'action': 'view', 'allowed': True}],
               'field_permissions': [{'entity_type': 'Project', 'field_name': 'name', 'can_view': True,
                                      'can_edit': False, 'mask_value': False}]}
    api = SimpleNamespace(org='tenant-a', call=lambda *a, **k: calls.append((a, k)))
    native = NativeConfiguration(api)
    native.get = lambda *a, **k: deepcopy(current)
    payload = {'entity_scope': ['Employee'], 'workflow_scope': ['onboarding'],
               'entity_permissions': [], 'field_permissions': [],
               'workflow_permissions': [{'machine_name': 'onboarding'}],
               'transition_permissions': [{'machine_name': 'onboarding', 'transition_key': 'approve'}]}
    native.write({'kind': 'role', 'key': 'role:hr', 'match': 'hr'}, payload, {'id': 'role-id'}, lambda _: None)
    first, second = calls[0][1]['json'], calls[1][1]['json']
    assert set(first) == {'workflow_permissions'}
    assert {'machine_name': 'onboarding'} in first['workflow_permissions']
    assert current['entity_permissions'][0] in second['entity_permissions']
    assert current['transition_permissions'][0] in second['transition_permissions']
    assert not {'permissions', 'name', 'users'} & second.keys()


def test_relationship_promotion_never_writes_record_edges():
    calls = []
    native = NativeConfiguration(SimpleNamespace(org='tenant-a', call=lambda *a, **k: calls.append((a, k))))
    payload = {'from_entity_type_id': 'source-type', 'to_entity_type_id': 'target-type',
               'relation_type': 'SNAPSHOT', 'relation_metadata': {}}
    native.write({'kind': 'relation', 'key': 'relation:test', 'match': '["Source","Target"]'}, payload, {}, lambda _: None)
    assert calls[0][0] == ('POST', '/entity-types/source-type/relation-declarations')
    assert 'from_entity_id' not in calls[0][1]['json']


def test_grant_order_is_semantic_not_destination_uuid_order():
    from hrms_app.configuration_package import walk
    role = {'workflow_permissions': [{'machine_name': 'z'}, {'machine_name': 'a'}]}
    assert walk(role, lambda v: v)['workflow_permissions'] == [{'machine_name': 'a'}, {'machine_name': 'z'}]
