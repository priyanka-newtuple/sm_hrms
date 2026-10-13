"""Add native asset fields, picklists, form and permissions without replacing tenant edits."""
import psycopg

from .asset_catalog import ASSET
from .policy import permission_key


def install_asset_form(api, pack):
    methods = api.call('GET', '/method-library/methods', params={'entity_type': ASSET, 'limit': 100})['items']
    if methods:
        return methods[0]['method_id']
    picklists = api.call('GET', '/config/picklists')['items']
    bindings = {}
    for key, label, values in (
        ('asset_category', 'Asset categories', ['Laptop', 'Desktop', 'Monitor', 'Phone', 'Peripheral', 'Furniture', 'Other']),
        ('asset_condition', 'Asset conditions', ['New', 'Good', 'Fair', 'Damaged']),
    ):
        existing = next((p for p in picklists if p['name'] == label), None)
        if existing is None:
            existing = api.call('POST', '/config/picklists', json={'name': label,
                'options': [{'value': v, 'label': v} for v in values]})
        bindings[key] = {'picklist_id': existing['id'], 'enum_values': [o['value'] if isinstance(o, dict) else o for o in existing['options']]}
    types = api.call('GET', '/field-library/field-types')['items']
    links = []
    for field in pack.fields:
        key = field['field']
        existing = api.call('GET', '/field-library/fields', params={'search': key, 'limit': 200})['items']
        found = next((f for f in existing if f['identity']['field_key'] == key), None)
        if found is None:
            engine = {'date': 'datetime', 'integer': 'int', 'decimal': 'float'}.get(field['type'], field['type'])
            code = next(t['code'] for t in types if t['engine_type'] == engine and t['selectable'])
            found = api.call('POST', '/field-library/fields', json={'name': key.replace('_', ' ').title(),
                'field_key': key, 'field_type': code, 'settings': bindings.get(key, {})})
        links.append({'library_field_id': found['identity']['library_field_id'],
            'version_id': found['version']['version_id'], 'required': field.get('required', False)})
    method = api.call('POST', '/method-library/methods', json={
        'name': 'Asset inventory form', 'entity_types': [ASSET], 'fields': links})
    return method['identity']['method_id']


def install_asset_permissions(api, dsn):
    # Versioned bootstrap is application metadata only. Revoked grants are never re-added.
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS hrms_feature_setup (organization_id text, feature text, PRIMARY KEY (organization_id, feature))')
        with db.transaction():
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (api.org + ':assets-v1',))
            if db.execute('SELECT 1 FROM hrms_feature_setup WHERE organization_id=%s AND feature=%s', (api.org, 'assets-v1')).fetchone():
                return
            for action in ('view', 'manage'):
                api.call('POST', '/permissions', json={'namespace': 'hrms', 'resource': 'asset',
                    'action': action, 'description': 'View own assets' if action == 'view' else 'Manage asset inventory and issue assets'})
            for role in api.call('GET', '/roles'):
                if role['name'] == 'hrms_application_service':
                    continue
                detail = api.call('GET', f"/roles/{role['id']}")
                if detail['organization_id'] != api.org:
                    raise RuntimeError('Role belongs to another organization')
                keys = {p['permission_key'] for p in detail['permissions']}
                keys.add(permission_key(api.org, 'asset:view'))
                if role['name'] in {'superadmin', 'hrms_office_admin'}:
                    keys.add(permission_key(api.org, 'asset:manage'))
                api.call('PUT', f"/roles/{role['id']}", json={'permissions': [{'permission_key': k} for k in sorted(keys)]})
            db.execute('INSERT INTO hrms_feature_setup VALUES (%s,%s)', (api.org, 'assets-v1'))
