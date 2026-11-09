import pytest
from hrms_app.platform import Actor
from hrms_app.errors import AppError
from hrms_app.record_collaboration import authorize_record, comment_path

ACTOR = Actor('user', 'org', 'human-token', frozenset({'hrms_employee'}), frozenset())

class Platform:
    def __init__(self):
        self.calls = []
        self.org = 'org'
        self.data = {}
    def request(self, method, path, *, token, **kwargs):
        assert token == 'human-token'
        self.calls.append((method, path))
        if path.startswith('/entity-records/'):
            return {'organization_id': self.org, 'data': self.data}
        if path == '/entities/record/comments':
            return {'comments': [{'id': 'parent', 'entity_id': 'record', 'reply_count': 1}]}
        if path == '/comments/parent/replies':
            return {'comments': [{'id': 'reply', 'entity_id': 'record'}]}
        raise AssertionError(path)


def test_visibility_checked_before_native_read():
    platform = Platform()
    with pytest.raises(AppError):
        authorize_record(platform, ACTOR, 'secret', [{'entity_id': 'record'}])
    assert platform.calls == []


def test_human_token_and_organization_are_enforced():
    platform = Platform()
    authorize_record(platform, ACTOR, 'record', [{'id': 'record'}])
    platform.org = 'other'
    with pytest.raises(AppError):
        authorize_record(platform, ACTOR, 'record', [{'id': 'record'}])


def test_onboarding_employee_can_only_access_linked_record():
    platform = Platform()
    actor = Actor('user', 'org', 'human-token', frozenset({'hrms_onboarding_employee'}), frozenset())
    with pytest.raises(AppError):
        authorize_record(platform, actor, 'record', [{'entity_id': 'record'}])
    platform.data = {'platform_user_id': 'user'}
    authorize_record(platform, actor, 'record', [{'entity_id': 'record'}])


def test_comment_and_reply_binding_verified_against_visible_native_data():
    platform = Platform()
    assert comment_path(platform, ACTOR, 'record') == '/entities/record/comments'
    assert comment_path(platform, ACTOR, 'record', 'parent', 'like') == '/comments/parent/like'
    assert comment_path(platform, ACTOR, 'record', 'reply') == '/comments/reply'
    with pytest.raises(AppError):
        comment_path(platform, ACTOR, 'record', 'someone-elses-comment')

@pytest.fixture
def surface(monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from hrms_app.main import create_app
    import hrms_app.employee_work as work
    entity = '11111111-1111-1111-1111-111111111111'
    comment = '22222222-2222-2222-2222-222222222222'
    calls = []
    platform = Platform()
    platform.actor = lambda token: ACTOR
    platform.request = lambda method, path, **kw: (
        {'organization_id': 'org', 'data': {}} if path.startswith('/entity-records/') else
        {'comments': [{'id': comment, 'entity_id': entity}]} if path.endswith('/comments') else
        {'items': [], 'total': 0, 'entity_id': kw['params']['entity_id']})
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True})
    platform.http = httpx.Client(base_url='http://core/v1/api/', transport=httpx.MockTransport(upstream))
    monkeypatch.setattr(work, 'employee_enrollments', lambda *args: [{'entity_id': entity}])
    return TestClient(create_app(platform, object()), headers={'Authorization': 'Bearer human-token'}), calls, entity, comment


def test_scoped_routes_preserve_human_identity_and_comment_operations(surface):
    client, calls, entity, comment = surface
    root = f'/v1/api/hrms/records/{entity}/employee'
    for method, path, payload in [('GET', '/comments', None), ('POST', '/comments', {'text': 'A note'}),
                                  ('PATCH', f'/comments/{comment}', {'text': 'Updated'}),
                                  ('POST', f'/comments/{comment}/replies', {'text': 'Reply'}),
                                  ('POST', f'/comments/{comment}/like', None),
                                  ('DELETE', f'/comments/{comment}', None)]:
        response = client.request(method, root + path, json=payload)
        assert response.status_code == 200
        assert calls[-1].headers['authorization'] == 'Bearer human-token'
        assert calls[-1].method == method
    assert client.get(root + '/activity?entity_id=other').json()['entity_id'] == entity
    assert client.get(root + '/activity?limit=500').status_code == 422
    assert client.post(root + f'/comments/{comment}/transition').status_code == 404
    assert client.get(root.replace(entity, '33333333-3333-3333-3333-333333333333') + '/comments').status_code == 404


def test_document_authorization_uses_file_owner_not_unrelated_offboarding_permission(monkeypatch):
    from types import SimpleNamespace
    from hrms_app.record_collaboration import authorize_document
    import hrms_app.employee_work as employee_work
    calls = []
    def request(method, path, *, token):
        assert token == ACTOR.token
        if path == '/filehandler/document':
            return {'owner_entity_id': 'employee'}
        return {'organization_id': 'org', 'entity_type_id': 'employee-type'}
    p = SimpleNamespace(request=request, call=lambda *a: {'entity_type_id': 'employee-type'})
    monkeypatch.setattr(employee_work, 'authorize_employee_file', lambda *a: calls.append(a))
    offboarding = SimpleNamespace(authorize_file=lambda *a: pytest.fail('Wrong module authorization'))
    authorize_document(p, ACTOR, 'GET', 'filehandler/document/download', {}, offboarding)
    assert len(calls) == 1
    p.request = lambda *a, **k: {'owner_entity_id': 'employee', 'organization_id': 'other'}
    with pytest.raises(AppError, match='organization'):
        authorize_document(p, ACTOR, 'GET', 'filehandler/document/download', {}, offboarding)
    assert len(calls) == 1


def test_metadata_only_exposes_native_granted_controls():
    from types import SimpleNamespace
    from hrms_app.record_collaboration import metadata
    from dataclasses import replace
    actor = replace(ACTOR, entity_permissions=(
        {'entity_type': 'HRMS.Employee', 'action': 'edit', 'allowed': True},
        {'entity_type': 'HRMS.Employee', 'action': 'delete', 'allowed': False},
        {'entity_type': 'HRMS.Asset', 'action': 'delete', 'allowed': True}))
    p = SimpleNamespace(call=lambda method, path: {'items': [{'entity_type_id': 'asset-type', 'name': 'HRMS.Asset'}]})
    record = {'entity_id': 'employee', 'entity_type_id': 'employee-type'}
    rows = [{'entity_id': 'employee', 'workflow_id': 'onboard', 'entity_type': 'HRMS.Employee', 'current_state': 'Review'}]
    data = metadata(p, actor, record, rows, 'onboard')
    assert data['can_edit_due_date'] and not data['can_archive']
    assert data['current_state'] == 'Review'
    assert not metadata(p, actor, record, rows, 'other')['can_edit_due_date']
    # Inventory rows carry `id`/`state` only; the native record supplies the type.
    asset = metadata(p, actor, {'entity_id': 'asset', 'entity_type_id': 'asset-type'}, [{'id': 'asset', 'state': 'issued'}])
    assert asset['can_archive'] and asset['current_state'] == 'issued' and not asset['can_edit_due_date']


def test_record_writes_keep_human_permission_enforcement(monkeypatch):
    from fastapi.testclient import TestClient
    from hrms_app.main import create_app
    import hrms_app.employee_work as work
    entity = '11111111-1111-1111-1111-111111111111'
    calls = []
    platform = Platform()
    platform.actor = lambda token: ACTOR
    def request(method, path, *, token, **kwargs):
        assert token == ACTOR.token
        calls.append((method,path,kwargs))
        if method == 'GET': return {'organization_id':'org','data':{}}
        raise AppError(403,'Native permission denied')
    platform.request = request
    monkeypatch.setattr(work,'employee_enrollments',lambda *args:[{'entity_id':entity}])
    client = TestClient(create_app(platform,object()),headers={'Authorization':'Bearer human-token'})
    root = f'/v1/api/hrms/records/{entity}/employee'
    assert client.put(root+'/due-date',json={'due_date':'2026-12-01'}).status_code == 403
    assert calls[-1] == ('PUT',f'/entity-records/{entity}',{'json':{'due_date':'2026-12-01'}})
    assert client.delete(root).status_code == 403
    assert calls[-1][0] == 'DELETE'
    before = len(calls)
    assert client.delete(root.replace(entity,'33333333-3333-3333-3333-333333333333')).status_code == 404
    assert len(calls) == before
