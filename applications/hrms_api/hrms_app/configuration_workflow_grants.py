"""Preserve access to version-pinned cases across native workflow publication."""
from .configuration_package import ConfigurationError


def projected_grants(grants, machine, old, new):
    """Expected native publish cascade; fail closed if native behavior changes."""
    before, after = old.get('transitions', []), new.get('transitions', [])
    route = lambda t: (t.get('from', t.get('from_state')), t.get('to_state'))
    old_keys = {t['key'] for t in before}
    new_keys = {t['key'] for t in after}
    removed, added = old_keys - new_keys, new_keys - old_keys
    routes = {route(t): t['key'] for t in after if t['key'] in added}
    renamed, unmatched = {}, []
    for index, t in enumerate(before):
        if t['key'] not in removed:
            continue
        if route(t) in routes:
            renamed[t['key']] = routes[route(t)]
        else:
            unmatched.append((index, t['key']))
    deleted = []
    if len(before) == len(after) and unmatched:
        candidates = {i: t['key'] for i, t in enumerate(after) if t['key'] in added and t['key'] not in renamed.values()}
        for i, key in unmatched:
            if i in candidates:
                renamed[key] = candidates[i]
            else:
                deleted.append(key)
    else:
        deleted = [key for _, key in unmatched]
    if not renamed and not deleted:
        return grants
    return {(m, renamed.get(k, k)) for m, k in grants if m != machine or renamed.get(k, k) in new_keys}


def capture(native, machine, old, new):
    if {t['key'] for t in old.get('transitions', [])} <= {t['key'] for t in new.get('transitions', [])}:
        return []
    snapshots = []
    for summary in native.listing('/roles'):
        role = native.get('/roles/' + summary['id'])
        grants = {(p['machine_name'], p['transition_key']) for p in role['transition_permissions']}
        if any(m == machine for m, _ in grants):
            snapshots.append({'id': role['id'], 'before': sorted(grants),
                              'expected': sorted(projected_grants(grants, machine, old, new)),
                              'workflow_access': sorted(p['machine_name'] for p in role['workflow_permissions'])})
    return snapshots


def restore(native, snapshots):
    for saved in snapshots:
        role = native.get('/roles/' + saved['id'])
        actual = sorted((p['machine_name'], p['transition_key']) for p in role['transition_permissions'])
        access = sorted(p['machine_name'] for p in role['workflow_permissions'])
        if actual != saved['expected'] or access != saved['workflow_access']:
            raise ConfigurationError('Role grants changed during workflow publication; review before recovery')
        if actual != saved['before']:
            native.api.call('PUT', '/roles/' + saved['id'], json={
                'transition_permissions': [{'machine_name': m, 'transition_key': k} for m, k in saved['before']]})
