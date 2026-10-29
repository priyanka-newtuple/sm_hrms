"""Allowlisted native configuration API adapter; never reads business records."""
from copy import deepcopy
from urllib.parse import quote

from .configuration_package import ConfigurationError, FIELDS, reference, walk
from .errors import AppError

GRANTS = {
    'entity_permissions': {'entity_type', 'action', 'allowed', 'entity_field', 'operator', 'value_source', 'condition_value', 'read_filter'},
    'field_permissions': {'entity_type', 'field_name', 'can_view', 'can_edit', 'mask_value'},
    'workflow_permissions': {'machine_name'},
    'transition_permissions': {'machine_name', 'transition_key'},
}


def sorted_grants(rows, names):
    import json
    return sorted((subset(row, names) for row in rows), key=lambda row: json.dumps(row, sort_keys=True))


def path(value):
    return quote(str(value), safe='')


def subset(value, names):
    return {name: deepcopy(value.get(name)) for name in names if name in value}


class NativeConfiguration:
    def __init__(self, api, bindings=None):
        self.api = api
        self.cache = {}
        self.bindings = dict(bindings or {})

    def get(self, route, **kwargs):
        value = self.api.call('GET', route, **kwargs)
        self.check_tenant(value)
        return value

    def check_tenant(self, value):
        if isinstance(value, dict):
            if value.get('organization_id') not in (None, self.api.org):
                raise ConfigurationError('Configuration response belongs to another tenant')
            for item in value.values():
                self.check_tenant(item)
        elif isinstance(value, list):
            for item in value:
                self.check_tenant(item)

    def listing(self, route, *, paged=False):
        if route not in self.cache:
            items, offset = [], 0
            while True:
                result = self.get(route, **({'params': {'limit': 100, 'offset': offset}} if paged else {}))
                batch = result['items'] if isinstance(result, dict) else result
                items.extend(batch)
                offset += len(batch)
                if not paged or offset >= result['total']:
                    break
                if not batch:
                    raise ConfigurationError('Incomplete native configuration pagination')
            self.cache[route] = items
        return self.cache[route]

    @staticmethod
    def unique(rows, predicate, label):
        matches = [row for row in rows if predicate(row)]
        if len(matches) > 1:
            raise ConfigurationError(f'Ambiguous configuration identity: {label}')
        return matches[0] if matches else None

    def read(self, obj):
        kind, match = obj['kind'], obj['match']
        identity, row = {}, None
        if kind == 'entity':
            try:
                row = self.get('/entity-types/' + path(match))
            except AppError as exc:
                if exc.status != 404:
                    raise
            if row:
                identity = {'id': row['entity_type_id']}
        elif kind in {'relation', 'named_relation'}:
            import json
            parts = json.loads(match)
            source, target = parts[:2]
            _, left = self.read({'kind': 'entity', 'match': source, 'key': 'entity:' + source})
            _, right = self.read({'kind': 'entity', 'match': target, 'key': 'entity:' + target})
            if left and right:
                route = '/relations' if kind == 'named_relation' else '/relation-declarations'
                rows = self.get('/entity-types/' + path(left['id']) + route)['items']
                row = self.unique(rows, lambda r: r['to_entity_type_id'] == right['id'] and
                                  (r.get('relation_name') == parts[2] if kind == 'named_relation' else not r.get('relation_name')), match)
                if row:
                    identity = {'id': row['relation_def_id']}
        elif kind == 'workflow':
            rows = self.get('/workflow-state-machines', params={'scope': 'published'})['published_items']
            row = self.unique(rows, lambda r: r['entity_type'] == match and r['is_active'], match)
            if row:
                row = self.get('/workflow-state-machines/' + path(row['id']))
                identity = {'id': row['id'], 'machine_name': row['machine_name']}
                row = subset(row, FIELDS[kind])
                row['definition']['machine_key'] = match
                row['definition'].pop('method_schemas', None)
                # Native publication regenerates method-derived fields from the
                # pinned methods. Transporting this cached projection causes
                # stale dropdowns and false differences after dependency repins.
                schema = row['definition'].get('entity_schema', {})
                if 'fields' in schema:
                    schema['fields'] = [f for f in schema['fields'] if not f.get('source_states')]
        elif kind == 'field':
            rows = self.listing('/field-library/fields', paged=True)
            row = self.unique(rows, lambda r: r['identity']['field_key'] == match, match)
            if row:
                if row['identity'].get('is_archived'):
                    raise ConfigurationError(f'Archived field: {match}')
                identity = {'id': row['identity']['library_field_id'], 'version_id': row['version']['version_id']}
                row = {**row['version'], 'field_key': row['identity']['field_key'], 'name': row['identity']['name']}
        elif kind == 'method':
            rows = self.listing('/method-library/methods', paged=True)
            bound = self.bindings.get(obj['key'])
            row = self.unique(rows, lambda r: r['method_id'] == bound if bound else r['name'] == match, match)
            if bound and row is None:
                raise ConfigurationError(f'Mapped method is missing: {obj["key"]}')
            if row:
                row = self.get('/method-library/methods/' + path(row['method_id']))
                if row['identity'].get('is_archived') or row['version'].get('connector_id'):
                    raise ConfigurationError(f'Archived or connector-backed method needs a binding: {match}')
                identity = {'id': row['identity']['method_id'], 'version_id': row['version']['version_id']}
                links = []
                for field in row['fields']:
                    link = subset(field, {'library_field_id', 'label', 'placeholder', 'required', 'position',
                                          'inherit_from', 'source_entity_type', 'source_field_key', 'ownership'})
                    link['version_id'] = field['field_version_id']
                    links.append(link)
                row = {**row['identity'], 'fields': links}
        elif kind == 'form':
            rows = self.listing('/forms/config')
            row = self.unique(rows, lambda r: r['schema_key'] == match, match)
            if row:
                identity = {'id': row.get('id', row['schema_key'])}
        elif kind == 'picklist':
            rows = self.listing('/config/picklists')
            row = self.unique(rows, lambda r: r['name'] == match, match)
            if row:
                identity = {'id': row['id']}
        elif kind == 'template':
            rows = self.listing('/email-templates')
            # System templates are shared, not tenant configuration to promote.
            row = self.unique(rows, lambda r: r['name'] == match and not r.get('is_system'), match)
            if row:
                identity = {'id': row['template_id']}
        elif kind == 'role':
            row = self.unique(self.listing('/roles'), lambda r: r['name'] == match, match)
            if row:
                row = self.get('/roles/' + path(row['id']))
                identity = {'id': row['id']}
                scope = obj['payload']
                machines = []
                for ref in scope['workflow_scope']:
                    if isinstance(ref, dict):
                        entity = ref['$ref'].removeprefix('workflow:')
                        _, wf = self.read({'kind': 'workflow', 'match': entity, 'key': ref['$ref']})
                        machines.append(wf.get('machine_name', ref))
                    else:
                        machines.append(ref)
                result = {'entity_scope': scope['entity_scope'], 'workflow_scope': machines}
                for name, names in GRANTS.items():
                    field, values = ('entity_type', scope['entity_scope']) if name.startswith(('entity_', 'field_')) else ('machine_name', machines)
                    result[name] = sorted_grants([p for p in row[name] if p[field] in values], names)
                row = result
        else:
            raise ConfigurationError(f'Unsupported configuration kind: {kind}')
        return (subset(row, FIELDS[kind]), identity) if row is not None else (None, {})

    def snapshot(self, objects):
        self.cache.clear()
        raw, identities, inverse = {}, {}, {}
        for obj in objects:
            payload, identity = self.read(obj)
            identities[obj['key']] = identity
            if payload is not None:
                raw[obj['key']] = {**obj, 'payload': payload}
                for attr, value in identity.items():
                    inverse[value] = reference(obj['key'], attr)
        def replace(value):
            return inverse.get(value, value) if isinstance(value, str) else value
        normalized = {key: {**obj, 'payload': walk(obj['payload'], replace)} for key, obj in raw.items()}
        return normalized, identities

    def preflight(self, objects, identities):
        """Read-only checks for unsupported edits before any resource is written."""
        from .configuration_package import resolve
        for obj in objects:
            current, identity = self.read(obj)
            if obj['kind'] == 'method':
                duplicates = [o for o in objects if o['kind'] == 'method' and o['match'] == obj['match']]
                if len(duplicates) > 1 and obj['key'] not in self.bindings:
                    raise ConfigurationError('Duplicate method names require explicit destination bindings')
            if not current:
                if obj['kind'] == 'role':
                    raise ConfigurationError('Create the destination role through native Settings before promoting scoped grants')
                continue
            if obj['kind'] == 'workflow':
                try:
                    changed = current != resolve(obj['payload'], identities)
                except ConfigurationError:
                    changed = True  # a dependency will be created by this release
                if changed:
                    drafts = self.get('/workflow-state-machines', params={'scope': 'draft', 'machine_name': identity['machine_name']})['draft_items']
                    if drafts:
                        raise ConfigurationError('Existing workflow draft must be resolved before promotion')
            if obj['kind'] == 'field' and current['name'] != obj['payload']['name']:
                raise ConfigurationError('Field renaming requires a reviewed Settings migration')
            if obj['kind'] == 'method':
                names = FIELDS['method'] - {'fields'}
                if subset(current, names) != resolve(subset(obj['payload'], names), identities):
                    raise ConfigurationError('Method metadata changes require a reviewed Settings migration')
            if obj['kind'] == 'entity':
                before = {f['field']: f.get('type') for f in current.get('schema_definition', {}).get('fields', [])}
                after = {f['field']: f.get('type') for f in obj['payload'].get('schema_definition', {}).get('fields', [])}
                if any(k not in after or after[k] != t for k, t in before.items()):
                    raise ConfigurationError('Entity field removal/type changes require a separate migration')
            if obj['kind'] == 'relation' and current.get('relation_type') != obj['payload'].get('relation_type'):
                raise ConfigurationError('Relationship type changes require a separate migration')
            if obj['kind'] == 'named_relation' and current != resolve(obj['payload'], identities):
                raise ConfigurationError('Existing named relationships cannot be changed by promotion')

    def write(self, obj, payload, identity, checkpoint):
        """Apply one allowlisted object. Checkpoint workflow drafts before publishing."""
        kind, match = obj['kind'], obj['match']
        call, existing = self.api.call, bool(identity)
        if kind == 'entity':
            call('PUT' if existing else 'POST', '/entity-types/' + path(match) if existing else '/entity-types', json=payload)
        elif kind == 'named_relation':
            if existing:
                raise ConfigurationError('Named relationship updates are not supported')
            call('POST', '/entity-types/' + path(payload['from_entity_type_id']) + '/relations',
                 json={k: v for k, v in payload.items() if k != 'from_entity_type_id'})
        elif kind == 'relation':
            if existing:
                call('PATCH', '/entity-types/relation-declarations/' + path(identity['id']),
                     json={'relation_metadata': payload['relation_metadata']})
            else:
                call('POST', '/entity-types/' + path(payload['from_entity_type_id']) + '/relation-declarations',
                     json={k: v for k, v in payload.items() if k != 'from_entity_type_id'})
        elif kind == 'picklist':
            call('PUT' if existing else 'POST', '/config/picklists/' + path(identity['id']) if existing else '/config/picklists', json=payload)
        elif kind == 'field':
            if existing:
                # One write per version; a name change requires manual migration to avoid partial updates.
                current, _ = self.read(obj)
                if current['name'] != payload['name']:
                    raise ConfigurationError('Field renaming must be reconciled in Settings before promotion')
                call('POST', '/field-library/fields/' + path(identity['id']) + '/versions',
                     json=subset(payload, {'field_type', 'description', 'settings'}))
            else:
                call('POST', '/field-library/fields', json=payload)
        elif kind == 'method':
            if existing:
                current, _ = self.read(obj)
                if subset(current, FIELDS[kind] - {'fields'}) != subset(payload, FIELDS[kind] - {'fields'}):
                    raise ConfigurationError('Method metadata changes must be reconciled in Settings before promotion')
                call('PUT', '/method-library/methods/' + path(identity['id']) + '/fields', json={'fields': payload['fields']})
            else:
                call('POST', '/method-library/methods', json=payload)
        elif kind == 'template':
            call('PUT' if existing else 'POST', '/email-templates/' + path(identity['id']) if existing else '/email-templates', json=payload)
        elif kind == 'form':
            call('PUT' if existing else 'POST', '/forms/config/' + path(match) if existing else '/forms/config',
                 json={k: v for k, v in payload.items() if not existing or k != 'schema_key'})
        elif kind == 'workflow':
            graph = deepcopy(payload['definition'])
            if existing:
                graph['machine_key'] = identity['machine_name']
                validation = call('POST', '/workflow-state-machines/validate',
                                  json={'machine_name': identity['machine_name'], 'definition': graph})
                if not validation.get('can_publish'):
                    raise ConfigurationError(f'Native workflow validation failed: {obj["key"]}')
                drafts = self.get('/workflow-state-machines', params={'scope': 'draft', 'machine_name': identity['machine_name']})['draft_items']
                if drafts:
                    raise ConfigurationError('Existing workflow draft must be resolved in Settings before promotion')
                draft = call('POST', '/workflow-state-machines/' + path(identity['machine_name']) + '/draft')
            else:
                # Native publication performs full validation for the newly allocated family.
                recovery = getattr(self, 'recovery_drafts', {}).get(obj['key'])
                if recovery:
                    from .configuration_package import digest
                    draft = self.get('/workflow-state-machines/' + path(recovery['id']))
                    if draft.get('version') != 0 or digest(draft) != recovery['checksum']:
                        raise ConfigurationError('Reviewed workflow draft changed before publication')
                else:
                    draft = call('POST', '/workflow-state-machines/draft', json={'name': graph['name']})
                graph['machine_key'] = draft['machine_name']
            from .configuration_workflow_grants import capture, restore
            old = self.get('/workflow-state-machines/' + identity['id'])['definition'] if existing else {}
            retained = capture(self, draft['machine_name'], old, graph)
            checkpoint({'draft_id': draft['id'], 'machine_name': draft['machine_name'], 'retained_transition_grants': retained})
            call('POST', '/workflow-state-machines/' + path(draft['id']) + '/publish',
                 json={'definition': graph, 'canvas_metadata': payload.get('canvas_metadata')})
            restore(self, retained)
        elif kind == 'role':
            current = self.get('/roles/' + path(identity['id']))
            merged = {}
            for name, names in GRANTS.items():
                field, values = ('entity_type', payload['entity_scope']) if name.startswith(('entity_', 'field_')) else ('machine_name', payload['workflow_scope'])
                unrelated = [p for p in current[name] if p[field] not in values]
                merged[name] = sorted_grants(unrelated, names) + payload[name]
            # The platform checks transition grants against workflow access.
            # Do not mutate global permissions, role identity or user memberships.
            all_access = {p['machine_name'] for p in current['workflow_permissions']} | {p['machine_name'] for p in merged['workflow_permissions']}
            call('PUT', '/roles/' + path(identity['id']), json={'workflow_permissions': [{'machine_name': m} for m in sorted(all_access)]})
            checkpoint({'workflow_access_written': True})
            call('PUT', '/roles/' + path(identity['id']), json=merged)
        else:
            raise ConfigurationError('Unsupported write')
        self.cache.clear()


def export_package(native, entity_types, name='hrms-core', roles=()):
    """Export selected workflows and recursively referenced supported definitions.

    Exact historic method pins, connectors and unknown IDs block export; they are
    never replaced with latest or silently removed.
    """
    specs, source_ids = {}, {}

    def add(kind, match, source_id=None):
        if source_id in source_ids:
            return source_ids[source_id]['$ref']
        key = kind + ':' + match
        if source_id and kind == 'method':
            suffix = 1
            while key in specs:
                suffix += 1
                key = kind + ':' + match + ':' + str(suffix)
            native.bindings[key] = source_id
        if key in specs:
            return key
        obj = {'key': key, 'kind': kind, 'match': match, 'payload': {}}
        payload, identity = native.read(obj)
        if payload is None:
            raise ConfigurationError(f'Missing source configuration: {key}')
        obj['payload'] = payload
        specs[key] = obj
        for attr, value in identity.items():
            source_ids[value] = reference(key, attr)
        return key

    # Build an index of identities to discover references without reading any records.
    index = {}
    for kind, route, paged, idkey, namekey in [
        ('method', '/method-library/methods', True, 'method_id', 'name'),
        ('picklist', '/config/picklists', False, 'id', 'name'),
        ('template', '/email-templates', False, 'template_id', 'name'),
    ]:
        for item in native.listing(route, paged=paged):
            if not item.get('is_system'):
                index[item[idkey]] = (kind, item[namekey])
    for item in native.listing('/field-library/fields', paged=True):
        index[item['identity']['library_field_id']] = ('field', item['identity']['field_key'])

    for entity in entity_types:
        add('entity', entity)
        add('workflow', entity)
        for form in native.get('/forms/config', params={'entity_type': entity})['items']:
            add('form', form['schema_key'])
        for item in native.listing('/email-templates'):
            if item.get('entity_type') == entity and not item.get('is_system'):
                add('template', item['name'])
    # Include actual relationship declarations and their entity definitions, but
    # never the relationship edges between employees or other runtime records.
    import json
    all_types = native.listing('/entity-types')
    type_names = {item['entity_type_id']: item['name'] for item in all_types}
    for entity in entity_types:
        source = native.get('/entity-types/' + path(entity))
        rows = native.get('/entity-types/' + path(source['entity_type_id']) + '/relation-declarations', params={'direction': 'both'})['items']
        legacy = native.get('/entity-types/' + path(source['entity_type_id']) + '/relations')['items']
        for row in [*rows, *legacy]:
            left, right = type_names[row['from_entity_type_id']], type_names[row['to_entity_type_id']]
            add('entity', left)
            add('entity', right)
            named = bool(row.get('relation_name'))
            match = [left, right, row['relation_name']] if named else [left, right]
            add('named_relation' if named else 'relation', json.dumps(match, separators=(',', ':')))
    scanned = set()
    while set(specs) - scanned:
        for key in sorted(set(specs) - scanned):
            scanned.add(key)
            def discover(value):
                if isinstance(value, str) and value in index:
                    add(*index[value], source_id=value)
                return value
            walk(specs[key]['payload'], discover)
    def replace(value):
        return source_ids.get(value, value) if isinstance(value, str) else value
    for role in sorted(roles):
        key = 'role:' + role
        spec = {'key': key, 'kind': 'role', 'match': role,
                'payload': {'entity_scope': sorted(entity_types),
                            'workflow_scope': [reference('workflow:' + entity, 'machine_name') for entity in sorted(entity_types)]}}
        payload, _ = native.read(spec)
        if payload is None:
            raise ConfigurationError(f'Missing source role: {role}')
        specs[key] = {**spec, 'payload': payload}
    objects = [{**obj, 'payload': walk(obj['payload'], replace)} for _, obj in sorted(specs.items())]
    package = {'schema_version': 1, 'name': name, 'objects': objects}
    from .configuration_package import validate
    validate(package)
    return package
