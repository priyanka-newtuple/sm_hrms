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
            if k != params[1] and o.result is None and o.progress.get('asset_plan')
            and (params[2] is None or o.progress.get('asset_target') == params[2] or 'asset_target' not in o.progress)), None))


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


def test_relation_failure_can_retry_without_reassigning_asset(system, monkeypatch):
    import hrms_app.onboarding_assets as links
    s,p,_=system
    aid=create(s)
    attempts=[]
    def relation(platform,asset,employee):
        attempts.append((asset,employee))
        if len(attempts)==1:raise AppError(503,'Temporary relationship failure')
    monkeypatch.setattr(links,'ensure_relation',relation)
    data={'issued_employee_id':'employee-one','issued_date':'2026-01-01'}
    with pytest.raises(AppError):command(s,'issue',data,aid)
    assert p.rows[aid]['state']=='issued'
    with pytest.raises(AppError):command(s,'issue',{**data,'issued_employee_id':'employee-two'},aid,key='different-key')
    command(s,'issue',data,aid)
    command(s,'issue',data,aid)
    assert attempts==[(aid,'employee-one'),(aid,'employee-one')]
    assert p.rows[aid]['data']['issued_employee_id']=='employee-one'


def test_same_employee_can_receive_multiple_assets(system):
    s,p,_=system
    first=create(s)
    second=command(s,'create',{'asset_tag':'NT-002','asset_name':'Monitor','asset_category':'Monitor','asset_condition':'Good'},key='create-monitor')['entity_id']
    for aid in (first,second):
        command(s,'issue',{'issued_employee_id':'employee-one','issued_date':'2026-01-01'},aid,key='issue-'+aid)
    assert len(s.board(actor('one','hrms_employee'))['items'])==2


def batch(s, ids, key='batch-operation', who=None, **data):
    from hrms_app.assets import AssetBatchCommand
    return s.assign_many(who or actor('admin', 'superadmin'), AssetBatchCommand(
        asset_ids=ids, idempotency_key=key, data={'issued_employee_id':'employee-one',
        'issued_date':'2026-01-01', **data}))


def pair(s):
    return [create(s), command(s, 'create', {'asset_tag':'NT-002', 'asset_name':'Monitor',
        'asset_category':'Monitor', 'asset_condition':'Good'}, key='second-create')['entity_id']]


def test_batch_partial_failure_retry_and_replay(system):
    s,p,j=system
    ids=pair(s)
    p.fail_trigger='issue'
    result=batch(s,ids)
    assert [r['status'] for r in result['items']]==['incomplete','assigned']
    assert batch(s,ids)['complete']
    count=len(j.audits)
    assert batch(s,ids)['complete']
    assert len(j.audits)==count
    assert len(s.board(actor('one','hrms_employee'))['items'])==2


def test_batch_preflight_rejects_without_any_assignments(system):
    s,p,_=system
    ids=pair(s)
    p.rows[ids[1]]['state']='issued'
    result=batch(s,ids)
    assert result['started'] is False
    assert p.rows[ids[0]]['state']=='available'
    assert not p.rows[ids[0]]['data'].get('issued_employee_id')
    assert batch(s,[ids[0],'foreign-asset'],key='foreign-batch')['started'] is False


def test_batch_permissions_duplicates_and_key_binding(system):
    s,_,_=system
    ids=pair(s)
    with pytest.raises(AppError):batch(s,ids,who=actor('one','hrms_employee'))
    with pytest.raises(AppError):batch(s,[ids[0],ids[0]])
    assert batch(s,ids)['complete']
    with pytest.raises(AppError):batch(s,ids,issued_employee_id='employee-two')


def test_unfinished_issue_does_not_block_unrelated_asset(system):
    s,p,_=system
    a,b=pair(s)
    p.fail_trigger='issue'
    with pytest.raises(AppError):
        command(s,'issue',{'issued_employee_id':'employee-one','issued_date':'2026-01-01'},a,key='failed-issue')
    command(s,'issue',{'issued_employee_id':'employee-two','issued_date':'2026-01-01'},b,key='other-issue')
    assert p.rows[b]['state']=='issued'


def test_batch_invalid_input_can_be_corrected_before_writes(system):
    s,p,_=system
    ids=pair(s)
    result=batch(s,ids,issued_date='not-a-date')
    assert result['started'] is False
    assert all(p.rows[i]['state']=='available' for i in ids)
    assert batch(s,ids,key='corrected-batch')['complete']


def test_pending_batches_scope_and_permission(system):
    from contextlib import contextmanager
    s,_,_=system
    calls=[]
    class DB:
        def execute(self, sql, params):
            calls.append((sql,params))
            return SimpleNamespace(fetchall=lambda: [({'idempotency_key':'saved-batch'},)])
    @contextmanager
    def lock(org):
        assert org=='org'
        yield DB()
    s.journal=SimpleNamespace(lock=lock)
    with pytest.raises(AppError):s.pending_batches(actor('one','hrms_employee'))
    assert not calls
    assert s.pending_batches(actor('admin','superadmin'))['items']==[{'idempotency_key':'saved-batch'}]
    assert calls[0][1]==('org','admin')
    assert 'organization_id=%s AND actor_id=%s' in calls[0][0]


def test_bulk_create_and_replay(system):
    from hrms_app.assets import AssetCreateBatchCommand
    s, p, j = system
    original = p.create_record
    def create_native(kind, data, owner):
        return original(kind, {**data, 'identifier': f'AST-{len(p.rows)}'}, owner)
    p.create_record = create_native
    cmd = AssetCreateBatchCommand(data={'asset_name': 'Monitor', 'asset_category':'Monitor', 'asset_condition':'Good'}, units=[{}, {}, {}], idempotency_key='bulk-create-1')
    result = s.create_many(actor('admin', 'superadmin'), cmd)
    assert result['complete'] and len(result['items']) == 3
    assert len({r['identifier'] for r in result['items']}) == 3
    assert s.create_many(actor('admin', 'superadmin'), cmd) == result
    assert len(p.records(ASSET, [])) == 3
    assert len(j.audits) == 3


def test_bulk_duplicate_validated_before_any_creation(system):
    from hrms_app.assets import AssetCreateBatchCommand
    s, p, _ = system
    cmd = AssetCreateBatchCommand(data={'asset_name': 'Monitor', 'asset_category':'Monitor', 'asset_condition':'Good'}, units=[{'serial_number':'ABC'}, {'serial_number':' abc '}], idempotency_key='bulk-duplicate')
    result = s.create_many(actor('admin', 'superadmin'), cmd)
    assert result['started'] is False
    assert p.records(ASSET, []) == []


def test_bulk_retry_completed_children_not_duplicated(system):
    from hrms_app.assets import AssetCreateBatchCommand
    s, p, j = system
    original = p.create_record
    attempts = []
    def failing(kind, data, owner):
        attempts.append(data)
        if len(attempts) == 2:
            raise AppError(422, 'Temporary rejection')
        return original(kind, data, owner)
    p.create_record = failing
    cmd = AssetCreateBatchCommand(data={'asset_name':'Monitor', 'asset_category':'Monitor', 'asset_condition':'Good'}, units=[{},{}], idempotency_key='bulk-retry-1')
    who = actor('admin','superadmin')
    result = s.create_many(who, cmd)
    assert not result['complete']
    assert len(p.records(ASSET, [])) == 1
    assert s.create_many(who, cmd)['complete']
    assert len(p.records(ASSET, [])) == 2
    assert len(j.audits) == 2


def test_bulk_forbidden_and_quantity_bounds(system):
    from hrms_app.assets import AssetCreateBatchCommand
    from pydantic import ValidationError
    s, p, _ = system
    for units in ([], [{}]*51):
        with pytest.raises(ValidationError):
            AssetCreateBatchCommand(data={},units=units,idempotency_key='bulk-bounds')
    cmd = AssetCreateBatchCommand(data={'asset_name':'Monitor', 'asset_category':'Monitor', 'asset_condition':'Good'}, units=[{}], idempotency_key='bulk-forbidden')
    with pytest.raises(AppError):
        s.create_many(actor('one','hrms_employee'),cmd)
    assert p.records(ASSET, []) == []


def test_bulk_recovers_lost_create_response(system):
    from hrms_app.assets import AssetCreateBatchCommand
    s,p,j=system
    original=p.create_record
    attempts=[]
    def lost(kind,data,owner):
        result=original(kind,data,owner)
        attempts.append(result)
        if len(attempts)==1:raise AppError(502,'Response lost')
        return result
    p.create_record=lost
    cmd=AssetCreateBatchCommand(data={'asset_name':'Monitor','asset_category':'Monitor','asset_condition':'Good'},units=[{},{}],idempotency_key='bulk-lost-response')
    who=actor('admin','superadmin')
    assert not s.create_many(who,cmd)['complete']
    assert s.create_many(who,cmd)['complete']
    assert len(p.records(ASSET,[]))==2
    assert len(attempts)==2
