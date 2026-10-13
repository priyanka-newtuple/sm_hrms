from types import SimpleNamespace
from dataclasses import replace

import pytest

from hrms_app.assets import AssetService, AssetCommand
from hrms_app.asset_catalog import ASSET
from hrms_app.catalog import pack_by_type
from hrms_app.errors import AppError
from hrms_app.service import HrmsService
from test_performance import Platform, Journal, actor


class AssetJournal(Journal):
    def execute(self, sql, params):
        return SimpleNamespace(fetchone=lambda: next(((k,) for k, o in self.ops.items()
            if k != params[1] and o.result is None and o.progress.get('asset_plan')), None))


@pytest.fixture
def system(monkeypatch):
    p, j = Platform(), AssetJournal()
    call = p.call
    def wrapped(method, path, **kwargs):
        if method == 'GET' and path.endswith('/transitions/available'):
            return {'available_transitions': [{'trigger': 'issue'}]}
        return call(method, path, **kwargs)
    p.call = wrapped
    fields = [dict(f) for f in pack_by_type(ASSET).fields]
    for f in fields:
        if f['field'] == 'asset_category':
            f['enum_values'] = ['Laptop', 'Monitor']
        if f['field'] == 'asset_condition':
            f['enum_values'] = ['Good']
    monkeypatch.setattr('hrms_app.assets.configured_form', lambda *args: {'fields': fields})
    p.add('HRMS.Employee', {'first_name': 'One', 'platform_user_id': 'one', 'employment_status': 'active'}, entity_id='employee-one')
    p.add('HRMS.Employee', {'first_name': 'Two', 'platform_user_id': 'two', 'employment_status': 'active'}, entity_id='employee-two')
    return AssetService(HrmsService(p, j, 'example.com')), p, j


def command(s, action, data, entity=None, key=None, who=None):
    return s.execute(who or actor('admin', 'superadmin'), entity, AssetCommand(action=action, data=data,
        idempotency_key=key or 'asset-key-' + action))


def create(s, **values):
    return command(s, 'create', {'asset_tag': 'NT-001', 'asset_name': 'Laptop', 'asset_category': 'Laptop',
        'asset_condition': 'Good', 'serial_number': 'SN1', 'asset_notes': 'Private inventory note', **values})['entity_id']


def test_inventory_issue_privacy_and_replay(system):
    s, p, j = system
    aid = create(s)
    assert s.board(actor('one', 'hrms_employee'))['items'] == []
    payload = {'issued_employee_id': 'employee-one', 'issued_date': '2026-01-01', 'issue_note': 'Charger included'}
    command(s, 'issue', payload, aid)
    command(s, 'issue', payload, aid)
    assert p.rows[aid]['state'] == 'issued'
    own = s.board(actor('one', 'hrms_employee'))
    assert len(own['items']) == 1
    assert own['items'][0]['actions'] == []
    assert 'asset_notes' not in own['items'][0]['data']
    assert own['employees'] == []
    assert s.board(actor('two', 'hrms_employee'))['items'] == []
    assert len(j.audits) == 2


def test_native_permissions_and_cross_record_scope(system):
    s, _, _ = system
    aid = create(s)
    for who in (actor('one', 'hrms_employee'), replace(actor('admin', 'superadmin'), permissions=frozenset())):
        with pytest.raises(AppError) as e:
            command(s, 'edit', {'asset_name': 'Changed'}, aid, who=who)
        assert e.value.status == 403
    with pytest.raises(AppError) as e:
        command(s, 'edit', {}, 'foreign-record')
    assert e.value.status == 404


def test_duplicate_identifiers_native_picklist_and_immutable_assignment(system):
    s, _, _ = system
    aid = create(s)
    with pytest.raises(AppError) as e:
        command(s, 'create', {'asset_tag': 'nt-001', 'asset_name': 'Other', 'asset_category': 'Laptop', 'asset_condition': 'Good'}, key='another-create')
    assert e.value.status == 409
    with pytest.raises(AppError):
        command(s, 'edit', {'asset_category': 'Invalid'}, aid, key='invalid-option')
    with pytest.raises(AppError):
        command(s, 'edit', {'issued_employee_id': 'employee-two'}, aid, key='bypass-issue')
    with pytest.raises(AppError):
        command(s, 'issue', {'issued_employee_id': 'foreign-employee', 'issued_date': '2026-01-01'}, aid)


def test_issue_failure_replay_prevents_reassignment(system):
    s, p, _ = system
    aid = create(s)
    p.fail_trigger = 'issue'
    data = {'issued_employee_id': 'employee-one', 'issued_date': '2026-01-01'}
    with pytest.raises(AppError):
        command(s, 'issue', data, aid)
    with pytest.raises(AppError) as e:
        command(s, 'issue', {**data, 'issued_employee_id': 'employee-two'}, aid, key='second-issue')
    assert e.value.status == 409
    command(s, 'issue', data, aid)
    assert p.rows[aid]['state'] == 'issued'
    with pytest.raises(AppError) as e:
        command(s, 'issue', {**data, 'issued_employee_id': 'employee-two'}, aid, key='second-issue')
    assert e.value.status == 409


def test_definite_workflow_rejection_restores_available_asset(system):
    s, p, _ = system
    aid = create(s)
    p.fail_trigger, p.fail_status = 'issue', 422
    with pytest.raises(AppError):
        command(s, 'issue', {'issued_employee_id': 'employee-one', 'issued_date': '2026-01-01'}, aid)
    assert not p.rows[aid]['data'].get('issued_employee_id')
    command(s, 'edit', {'asset_name': 'Updated'}, aid)
