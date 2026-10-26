"""Portable tenant configuration and conservative three-way promotion planning.

No runtime records or arbitrary HTTP operations are accepted by this format.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy


class ConfigurationError(ValueError):
    pass


KINDS = {'entity', 'picklist', 'field', 'method', 'form', 'template', 'workflow', 'role', 'relation', 'named_relation'}
UUID = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I)
FORBIDDEN = {'password', 'secret', 'client_secret', 'access_token', 'refresh_token', 'api_key',
             'organization_id', 'created_by', 'owner_id', 'assignee_id', 'user_id', 'connector_id'}
FIELDS = {
    'entity': {'name', 'description', 'schema_definition', 'is_active'},
    'picklist': {'name', 'options'},
    'field': {'name', 'field_key', 'field_type', 'description', 'settings'},
    'method': {'name', 'description', 'category_id', 'entity_types', 'fields'},
    'form': {'schema_key', 'name', 'description', 'entity_type', 'fields', 'is_active', 'display_order'},
    'template': {'name', 'subject', 'body_html', 'entity_type', 'form_id'},
    'workflow': {'definition', 'canvas_metadata'},
    'role': {'entity_scope', 'workflow_scope', 'entity_permissions', 'field_permissions',
             'workflow_permissions', 'transition_permissions'},
    'relation': {'from_entity_type_id', 'to_entity_type_id', 'relation_type', 'relation_metadata'},
    'named_relation': {'from_entity_type_id', 'to_entity_type_id', 'relation_name'},
}
REQUIRED = {
    'entity': {'name'}, 'picklist': {'name', 'options'},
    'field': {'name', 'field_key', 'field_type', 'settings'},
    'method': {'name', 'fields', 'entity_types'},
    'form': {'schema_key', 'name', 'entity_type', 'fields'},
    'template': {'name', 'subject', 'body_html'}, 'workflow': {'definition'},
    'role': {'entity_scope', 'workflow_scope'},
    'relation': FIELDS['relation'], 'named_relation': FIELDS['named_relation'],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def reference(key, attribute='id'):
    return {'$ref': key, 'attribute': attribute}


def walk(value, transform):
    if isinstance(value, dict):
        if '$ref' in value:
            return transform(value)
        result = {k: walk(v, transform) for k, v in value.items()}
        for key in ('entity_permissions', 'field_permissions', 'workflow_permissions', 'transition_permissions'):
            if isinstance(result.get(key), list):
                result[key] = sorted(result[key], key=lambda item: json.dumps(item, sort_keys=True))
        return result
    if isinstance(value, list):
        return [walk(v, transform) for v in value]
    return transform(value)


def references(value):
    found = set()
    def collect(v):
        if isinstance(v, dict) and '$ref' in v:
            found.add(v['$ref'])
        return v
    walk(value, collect)
    return found


def portable(value, path='payload'):
    """Reject unsafe material; never silently strip unknown embedded identifiers."""
    if isinstance(value, dict):
        if '$ref' in value:
            if set(value) != {'$ref', 'attribute'} or value['attribute'] not in {'id', 'version_id', 'machine_name'}:
                raise ConfigurationError(f'Invalid reference at {path}')
            return
        for key, item in value.items():
            dynamic_actor = key in {'user_id', 'owner_id', 'assignee_id'} and isinstance(item, str) and re.fullmatch(r'\$entity\.[A-Za-z_][A-Za-z0-9_]*', item)
            if key.lower() in FORBIDDEN and item not in (None, '', [], {}) and not dynamic_actor:
                raise ConfigurationError(f'Environment-specific value at {path}.{key}')
            portable(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            portable(item, f'{path}[{index}]')
    elif isinstance(value, str):
        if UUID.search(value):
            raise ConfigurationError(f'Unresolved environment identifier at {path}')
        # Template dynamic recipients are allowed; actual addresses and endpoints are not.
        if re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', value) or re.search(r'https?://', value, re.I):
            raise ConfigurationError(f'Literal address or URL needs review/binding at {path}')


def validate(package):
    if set(package) != {'schema_version', 'name', 'objects'} or package['schema_version'] != 1:
        raise ConfigurationError('Unsupported configuration package schema')
    if not isinstance(package['name'], str) or not package['name'].strip():
        raise ConfigurationError('Package name is required')
    if not isinstance(package['objects'], list) or not package['objects']:
        raise ConfigurationError('A release package must contain objects')
    objects = {}
    for obj in package['objects']:
        if set(obj) != {'key', 'kind', 'match', 'payload'} or obj['kind'] not in KINDS:
            raise ConfigurationError('Unsupported configuration object')
        key = obj['key']
        if not isinstance(key, str) or not key or key in objects:
            raise ConfigurationError('Duplicate or missing configuration key')
        if not isinstance(obj['match'], str) or not obj['match']:
            raise ConfigurationError(f'Missing stable selector: {key}')
        if not isinstance(obj['payload'], dict) or set(obj['payload']) - FIELDS[obj['kind']]:
            raise ConfigurationError(f'Unsupported payload properties: {key}')
        if REQUIRED[obj['kind']] - obj['payload'].keys():
            raise ConfigurationError(f'Missing required payload properties: {key}')
        selector = {'entity': 'name', 'picklist': 'name', 'field': 'field_key', 'method': 'name',
                    'form': 'schema_key', 'template': 'name'}.get(obj['kind'])
        if selector and obj['payload'][selector] != obj['match']:
            raise ConfigurationError(f'Payload identity does not match selector: {key}')
        portable(obj['payload'], key)
        objects[key] = obj
    for obj in objects.values():
        missing = references(obj['payload']) - objects.keys()
        if missing:
            raise ConfigurationError(f'Unresolved dependencies for {obj["key"]}: {sorted(missing)}')
        if obj['kind'] == 'role':
            scopes = obj['payload']
            if not scopes.get('entity_scope') or not scopes.get('workflow_scope'):
                raise ConfigurationError('Role promotion requires explicit entity and workflow scope')
            for entity in scopes['entity_scope']:
                if 'entity:' + entity not in objects:
                    raise ConfigurationError('Role scope must refer to a packaged entity')
            for ref in scopes['workflow_scope']:
                if not isinstance(ref, dict) or ref.get('attribute') != 'machine_name' or objects.get(ref.get('$ref'), {}).get('kind') != 'workflow':
                    raise ConfigurationError('Invalid workflow permission scope')
                target = objects[ref['$ref']]
                if target['key'] != 'workflow:' + target['match']:
                    raise ConfigurationError('Workflow scope needs a canonical workflow key')
            for name in ('entity_permissions', 'field_permissions'):
                if any(p['entity_type'] not in scopes['entity_scope'] for p in scopes.get(name, [])):
                    raise ConfigurationError('Permission outside managed entity scope')
            for name in ('workflow_permissions', 'transition_permissions'):
                if any(p['machine_name'] not in scopes['workflow_scope'] for p in scopes.get(name, [])):
                    raise ConfigurationError('Permission outside managed workflow scope')
    ordered, pending = [], dict(objects)
    while pending:
        priority = ['entity', 'picklist', 'field', 'relation', 'named_relation', 'method', 'form', 'template', 'workflow', 'role']
        ready = sorted((k for k, o in pending.items() if references(o['payload']) <= {x['key'] for x in ordered}),
                       key=lambda k: (priority.index(pending[k]['kind']), k))
        if not ready:
            raise ConfigurationError('Configuration dependency cycle')
        ordered.extend(pending.pop(k) for k in ready)
    return ordered


def make_plan(package, actual, baseline, organization):
    ordered = validate(package)
    expected = {o['key']: o for o in ordered}
    operations = []
    for key in sorted(set(expected) | set(baseline)):
        desired = expected.get(key)
        current, previous = actual.get(key), baseline.get(key)
        if desired is None:
            decision = 'retirement_required'
        elif current == desired:
            decision = 'unchanged' if previous else 'adopt'
        elif previous is None and current is None:
            decision = 'create'
        elif previous is not None and current == previous:
            decision = 'update'
        else:
            decision = 'conflict'
        operations.append({'key': key, 'decision': decision,
                           'before': digest(current), 'after': digest(desired)})
    result = {'organization': organization, 'package_name': package['name'],
              'package_checksum': digest(package), 'baseline_checksum': digest(baseline),
              'snapshot_checksum': digest(actual), 'operations': operations,
              'blocked': any(x['decision'] in {'conflict', 'retirement_required'} for x in operations)}
    result['plan_checksum'] = digest(result)
    return result


def verify_plan(plan, fresh):
    if plan != fresh or fresh['blocked']:
        raise ConfigurationError('Plan is stale or contains conflicts; generate and review a new plan')


def resolve(value, identities):
    def replace(v):
        if isinstance(v, dict) and '$ref' in v:
            try:
                result = identities[v['$ref']][v['attribute']]
            except KeyError as exc:
                raise ConfigurationError(f'Unresolved destination reference: {v["$ref"]}') from exc
            if not result:
                raise ConfigurationError(f'Missing destination identity: {v["$ref"]}')
            return result
        return v
    return walk(deepcopy(value), replace)
