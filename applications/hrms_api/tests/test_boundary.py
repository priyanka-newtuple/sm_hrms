from native_permissions import grants
from pathlib import Path
import ast

import httpx
import pytest
from fastapi.testclient import TestClient

from hrms_app.errors import AppError
from hrms_app.main import create_app
from hrms_app.platform import Actor, PlatformClient


def test_runtime_has_no_platform_imports_or_platform_database_access():
    forbidden = {'backend', 'entities', 'workflow', 'tasks', 'roles', 'user', 'organizations',
                 'database', 'common', 'forms', 'hrms_native', 'sqlalchemy'}
    root = Path(__file__).parents[1] / 'hrms_app'
    for path in root.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert not any(alias.name.split('.')[0] in forbidden for alias in node.names), path
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split('.')[0] not in forbidden, path


def test_entity_summary_reads_follow_cursor_and_tenant_boundary():
    calls = []
    def handler(request):
        calls.append(request.url.params)
        second = request.url.params.get('cursor') == 'page2'
        return httpx.Response(200, json={'items': [{'entity_id': str(second), 'organization_id': 'org',
            'summary_fields': {'first_name': 'Employee'}}], 'has_more': not second,
            'next_cursor': None if second else 'page2'})
    api = PlatformClient('http://platform/v1/api', 'org', 'service', 'secret', transport=httpx.MockTransport(handler))
    api.service_token = lambda: 'internal-token'
    assert len(api.records('HRMS.Employee', ['first_name'])) == 2
    assert calls[1]['cursor'] == 'page2'


@pytest.mark.parametrize('membership,status,org', [('suspended','active','org'), ('active','pending','org'), ('active','active','other')])
def test_actor_rejects_inactive_or_cross_tenant(membership, status, org):
    def handler(request):
        path = request.url.path
        if path.endswith('/auth/me'):
            data = {'id': 'user', 'status': status}
        elif path.endswith('/roles/my-permissions'):
            data = {'user_id': 'user', 'organization_id': org, 'roles': [], 'permissions': []}
        else:
            data = {'organizations': [{'organization_id': org, 'status': membership, 'organization_status': 'active'}]}
        return httpx.Response(200, json=data)
    api = PlatformClient('http://platform/v1/api', 'org', 'service', 'secret', transport=httpx.MockTransport(handler))
    with pytest.raises(AppError) as error:
        api.actor('user-token')
    assert error.value.status == 403


def test_gateway_blocks_native_mutation_bypasses_even_for_administrator():
    class Platform:
        def records(self, kind, fields):
            return []
        org = 'org'
        def actor(self, token):
            return Actor('admin', 'org', token, frozenset({'admin'}), grants({'admin'}))
    client = TestClient(create_app(Platform(), object()))
    for path in ['/entity-records', '/tasks/task-id', '/entities/entity-id/transitions',
                 '/workflow-state-machines/hrms_onboardingcase/enrollments', '/roles', '/auth/register', '/agent/chat']:
        response = client.post('/v1/api' + path, headers={'Authorization': 'Bearer admin'}, json={})
        assert response.status_code == 403, path


def test_employee_creation_requires_permission_before_upstream_writes():
    class Platform:
        org = "org"
        def records(self, kind, fields):
            return []
        def actor(self, token):
            return Actor('employee', 'org', token, frozenset({'hrms_employee'}), grants({'hrms_employee'}))
    client = TestClient(create_app(Platform(), object()))
    response = client.post('/v1/api/hrms/employees', headers={'Authorization': 'Bearer employee'}, json={
        'first_name': 'Test', 'last_name': 'Employee', 'work_email': 'test@newtuple.com',
        'department': 'Engineering', 'designation': 'Engineer', 'date_joined': '2026-09-28', 'idempotency_key': 'test-operation'})
    assert response.status_code == 403


def test_workflow_list_is_empty_not_forbidden_for_people_without_workflow_access():
    import httpx

    def platform_response(request):
        token = request.headers['authorization'].removeprefix('Bearer ')
        if token != 'admin':
            return httpx.Response(403, json={'detail': 'Forbidden'})
        return httpx.Response(200, json={'scope': 'all', 'published_items': [{'machine_name': 'wf'}], 'draft_items': []})

    class Platform:
        def records(self, kind, fields):
            return []
        org = 'org'
        http = httpx.Client(base_url='http://platform.test/', transport=httpx.MockTransport(platform_response))
        def actor(self, token):
            return Actor(token, 'org', token, frozenset({token}), grants({token}))
    client = TestClient(create_app(Platform(), object()))
    for role in ('hrms_employee', 'hrms_manager'):
        response = client.get('/v1/api/workflow-state-machines?scope=all', headers={'Authorization': f'Bearer {role}'})
        assert response.status_code == 200 and response.json() == {'scope': 'all', 'published_items': [], 'draft_items': []}
    admin = client.get('/v1/api/workflow-state-machines?scope=all', headers={'Authorization': 'Bearer admin'})
    assert admin.json()['published_items'] == [{'machine_name': 'wf'}]  # people with access still get the real list
    # Only the list read is softened: other refusals pass through unchanged.
    active = client.get('/v1/api/workflow-state-machines/wf/active', headers={'Authorization': 'Bearer hrms_employee'})
    assert active.status_code == 403
