from dataclasses import replace

import pytest

from hrms_app.errors import AppError
from hrms_app.platform import Actor
from hrms_app.policy import capabilities, permission_key, require
from hrms_app.permission_migration import legacy_grants


def test_role_names_no_longer_grant_business_access():
    person = Actor('u', 'org', 'token', frozenset({'hrms_hr_full', 'superadmin'}), frozenset())
    assert capabilities(person) == set()
    with pytest.raises(AppError):
        require(person, 'employee:create')


def test_custom_native_role_grant_and_revocation_take_effect():
    person = Actor('u', 'org', 'token', frozenset({'custom_people_team'}),
                   frozenset({permission_key('org', 'employee:create')}))
    require(person, 'employee:create')
    with pytest.raises(AppError):
        require(replace(person, permissions=frozenset()), 'employee:create')
    assert capabilities(replace(person, organization_id='another')) == set()


def test_account_approval_and_settings_remain_superadmin_only():
    person = Actor('u', 'org', 'token', frozenset({'custom_role'}), frozenset({'settings:access', 'user:write',
        permission_key('org', 'employee:activate'), permission_key('org', 'platform:configure')}))
    assert capabilities(person) == set()
    assert capabilities(replace(person, roles=frozenset({'superadmin'}))) == {'employee:activate', 'platform:configure'}


def test_migration_keeps_explicit_denials_and_custom_role_overrides():
    assert 'project:create' not in legacy_grants('hrms_project_manager', {'hrms_project_manager': []})
    assert legacy_grants('custom_role', {'custom_role': ['project:view']}, {'custom_role': ['cockpit:view']}) == {'project:view', 'cockpit:view'}


def test_migration_resumes_checkpoint_and_never_reapplies_after_completion(monkeypatch):
    from hrms_app import permission_migration as migration

    class Database:
        records = {}
        result = None
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params=()):
            self.result = None
            if sql.startswith('SELECT 1 FROM native_permission_migration'):
                self.result = (1,) if self.records.get('__complete__') else None
            elif sql.startswith('SELECT grants,completed'):
                self.result = self.records.get(params[1])
            elif sql.startswith('INSERT INTO native_permission_migration'):
                if "'__complete__'" in sql:
                    self.records['__complete__'] = True
                else:
                    self.records[params[1]] = (params[2].obj, False)
            elif sql.startswith('UPDATE native_permission_migration'):
                self.records[params[1]] = (self.records[params[1]][0], True)
            return self
        def fetchone(self): return self.result

    class API:
        org = 'org'
        fail = True
        writes = 0
        keys = {'entity_record:read'}
        def call(self, method, path, **kwargs):
            if path == '/permissions': return {}
            if path == '/roles': return [{'id': 'r', 'name': 'hrms_project_manager'}]
            if method == 'GET':
                return {'organization_id': self.org, 'permissions': [{'permission_key': k} for k in self.keys]}
            self.writes += 1
            if self.fail: raise RuntimeError('temporary API outage')
            self.keys = {p['permission_key'] for p in kwargs['json']['permissions']}

    db, api = Database(), API()
    monkeypatch.setattr(migration.psycopg, 'connect', lambda *args, **kwargs: db)
    monkeypatch.setattr(migration, 'legacy_policy', lambda *args: {})
    with pytest.raises(RuntimeError): migration.migrate_native_permissions(api, 'test')
    assert db.records['r'][1] is False
    api.fail = False
    migration.migrate_native_permissions(api, 'test')
    assert db.records['r'][1] is True
    assert 'entity_record:read' in api.keys
    assert permission_key('org', 'project:view') in api.keys
    api.keys = {'entity_record:read'}  # Super Admin subsequently revokes app access.
    writes = api.writes
    migration.migrate_native_permissions(api, 'test')
    assert api.writes == writes
    assert api.keys == {'entity_record:read'}
