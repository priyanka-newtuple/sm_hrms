"""One-time transfer of legacy HRMS policy into native roles via public APIs.

The JSON defaults and old app tables are migration inputs only. Runtime authorization
never reads them. Checkpoints preserve subsequent Super Admin changes on redeploy.
"""
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from .policy import permission_key

INITIAL_ROLE_GRANTS = json.loads(Path(__file__).with_name('initial_role_grants.json').read_text())
PROJECT = frozenset({'project:view', 'project:read_all', 'project:create', 'project:manage_assigned',
    'project:manage_all', 'project:commercial_assigned', 'project:commercial_all', 'project:approve',
    'customer:create', 'allocation:request'})
COCKPIT = frozenset({'cockpit:view', 'cockpit:author', 'cockpit:jobs', 'cockpit:approve', 'cockpit:publish'})
RESERVED = {'platform:configure', 'employee:activate'}


def legacy_grants(role, projects=None, cockpit=None):
    result = set(INITIAL_ROLE_GRANTS.get(role, []))
    for policy, family in ((projects or {}, PROJECT), (cockpit or {}, COCKPIT)):
        if role in policy:
            result = (result - family) | (set(policy[role]) & family)
    return result - RESERVED


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS native_permission_migration (
        organization_id text NOT NULL, role_id text NOT NULL, grants jsonb NOT NULL,
        completed boolean NOT NULL DEFAULT false, PRIMARY KEY (organization_id, role_id))""")


def migration_complete(dsn, organization_id):
    with psycopg.connect(dsn) as db:
        initialize(db)
        row = db.execute("SELECT completed FROM native_permission_migration WHERE organization_id=%s AND role_id='__complete__'",
                               (organization_id,)).fetchone()
        return bool(row and row[0])


def legacy_policy(db, table, organization_id):
    # Table names are internal constants; no browser-supplied SQL or platform table access.
    if not db.execute('SELECT to_regclass(%s)', (table,)).fetchone()[0]:
        return {}
    row = db.execute(f'SELECT roles FROM {table} WHERE organization_id=%s', (organization_id,)).fetchone()
    return row[0] if row else {}


def migrate_native_permissions(api, dsn):
    with psycopg.connect(dsn, autocommit=True) as db:
        initialize(db)
        db.execute('SELECT pg_advisory_lock(hashtextextended(%s, 0))', (api.org + ':native-permissions',))
        try:
            if db.execute("SELECT 1 FROM native_permission_migration WHERE organization_id=%s AND role_id='__complete__' AND completed",
                          (api.org,)).fetchone():
                return
            catalog = sorted(set().union(*map(set, INITIAL_ROLE_GRANTS.values())) - RESERVED)
            for capability in catalog:
                resource, action = capability.split(':')
                api.call('POST', '/permissions', json={'namespace': 'hrms', 'resource': resource, 'action': action,
                         'description': f"HRMS {resource.replace('_', ' ')}: {action.replace('_', ' ')}"})
            projects = legacy_policy(db, 'project_access_policy', api.org)
            cockpit = legacy_policy(db, 'cockpit_access_policy', api.org)
            roles = api.call('GET', '/roles')
            for role in roles:
                if role['name'] == 'hrms_application_service':
                    continue
                row = db.execute('SELECT grants,completed FROM native_permission_migration WHERE organization_id=%s AND role_id=%s',
                                 (api.org, role['id'])).fetchone()
                if row and row[1]:
                    continue
                desired = row[0] if row else sorted(legacy_grants(role['name'], projects, cockpit))
                if row is None:
                    db.execute('INSERT INTO native_permission_migration (organization_id,role_id,grants) VALUES (%s,%s,%s)',
                               (api.org, role['id'], Jsonb(desired)))
                current = api.call('GET', f"/roles/{role['id']}")
                if current['organization_id'] != api.org:
                    raise RuntimeError('Role belongs to another tenant')
                keys = {p['permission_key'] for p in current['permissions']}
                keys.update(permission_key(api.org, cap) for cap in desired)
                api.call('PUT', f"/roles/{role['id']}", json={'permissions': [{'permission_key': key} for key in sorted(keys)]})
                db.execute('UPDATE native_permission_migration SET completed=true WHERE organization_id=%s AND role_id=%s',
                           (api.org, role['id']))
            db.execute("INSERT INTO native_permission_migration (organization_id,role_id,grants,completed) VALUES (%s,'__complete__','[]',true)", (api.org,))
        finally:
            db.execute('SELECT pg_advisory_unlock(hashtextextended(%s, 0))', (api.org + ':native-permissions',))
