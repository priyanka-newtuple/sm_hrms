"""Tenant-scoped journal and promotion runner, stored only in the HRMS database."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

from .configuration_package import ConfigurationError, digest, make_plan, resolve, validate, verify_plan


class Journal:
    def __init__(self, dsn, organization, name):
        self.dsn, self.organization, self.name = dsn, organization, name

    @contextmanager
    def locked(self):
        with psycopg.connect(self.dsn, autocommit=True) as db:
            # Lock all packages in a tenant: packages may share native objects.
            lock = int(digest(['hrms-configuration', self.organization])[:15], 16)
            if not db.execute('SELECT pg_try_advisory_lock(%s)', (lock,)).fetchone()[0]:
                raise ConfigurationError('Another configuration promotion is running for this tenant')
            try:
                db.execute('''CREATE TABLE IF NOT EXISTS hrms_configuration_releases (
                    organization_id text NOT NULL, package_name text NOT NULL,
                    state jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (organization_id, package_name))''')
                self.db = db
                yield self
            finally:
                db.execute('SELECT pg_advisory_unlock(%s)', (lock,))

    def read(self):
        row = self.db.execute('SELECT state FROM hrms_configuration_releases WHERE organization_id=%s AND package_name=%s',
                              (self.organization, self.name)).fetchone()
        return row[0] if row else {'baseline': {}, 'status': 'not_applied'}

    def save(self, state):
        self.db.execute('''INSERT INTO hrms_configuration_releases (organization_id, package_name, state)
            VALUES (%s,%s,%s) ON CONFLICT (organization_id, package_name)
            DO UPDATE SET state=EXCLUDED.state, updated_at=now()''',
                        (self.organization, self.name, Jsonb(state)))


def inspection(native, package, state):
    objects = validate(package)
    baseline = state.get('baseline', {})
    # Keep removed objects in the snapshot so retirement cannot be mistaken for no-op.
    specs = {**baseline, **{o['key']: o for o in objects}}
    actual, identities = native.snapshot(list(specs.values()))
    return make_plan(package, actual, baseline, native.api.org), actual, identities


def adopt_reviewed(native, package, reviewed, journal):
    """Record an explicitly reviewed initial snapshot, then use normal promotion.

    The review binds the tenant, every before/after hash and the entire snapshot.
    This is not a force mode: stale reviews, existing releases and unsupported
    migrations are rejected before recording the adoption or writing native data.
    """
    state = journal.read()
    if state.get('baseline') or state.get('status') != 'not_applied':
        raise ConfigurationError('Initial adoption is only allowed for an unmanaged package')
    fresh, actual, identities = inspection(native, package, state)
    if fresh != reviewed or any(op['decision'] not in {'adopt', 'create', 'conflict'}
                               for op in fresh['operations']):
        raise ConfigurationError('Initial adoption review is stale or invalid')
    native.preflight(validate(package), identities)
    checked, _, _ = inspection(native, package, state)
    if checked != reviewed:
        raise ConfigurationError('Destination changed during initial adoption checks')
    state = {**state, 'status': 'adopted', 'baseline': deepcopy(actual),
             'adoption_review': deepcopy(reviewed),
             'bindings': {key: identity['id'] for key, identity in identities.items()
                          if key.startswith('method:') and identity}}
    journal.save(state)
    plan, _, _ = inspection(native, package, state)
    return apply(native, package, plan, journal)


def resume_reviewed(native, package, reviewed, journal):
    """Resume a failed, certain checkpoint only after an exact fresh review."""
    state = journal.read()
    if (state.get('status') != 'failed' or state.get('pending') is not None
            or state.get('package_checksum') != digest(package)):
        raise ConfigurationError('Recovery requires the same failed package with no uncertain write')
    objects = validate(package)
    fresh, actual, identities = inspection(native, package, {'baseline': {}})
    if fresh != reviewed:
        raise ConfigurationError('Recovery review is stale or invalid')
    by_key = {o['key']: o for o in objects}
    for key in state.get('completed', []):
        if key not in by_key:
            raise ConfigurationError('Unknown completed checkpoint')
        value, _ = native.read(by_key[key])
        if value != resolve(by_key[key]['payload'], identities):
            raise ConfigurationError('A completed configuration changed; recovery stopped')
    native.preflight(objects, identities)
    checked, _, _ = inspection(native, package, {'baseline': {}})
    if checked != reviewed:
        raise ConfigurationError('Destination changed during recovery checks')
    history = deepcopy(state.get('recovery_history', []))
    history.append({'review': deepcopy(reviewed), 'baseline': deepcopy(state.get('baseline', {})),
                    'completed': list(state.get('completed', [])),
                    'reviewed_at': datetime.now(timezone.utc).isoformat()})
    journal.save({**state, 'status': 'recovery_reviewed', 'baseline': deepcopy(actual),
                  'recovery_history': history})
    plan, _, _ = inspection(native, package, journal.read())
    # A fully completed checkpoint is finalized by reconcile, including all pins.
    if all(op['decision'] == 'unchanged' for op in plan['operations']):
        journal.save({**journal.read(), 'status': 'failed'})
        return reconcile(native, package, journal)
    return apply(native, package, plan, journal)


def apply(native, package, plan, journal):
    """Apply a previously reviewed exact plan; uncertain writes require reconciliation.

    Native APIs provide no cross-object transaction or conditional writes. The
    journal lock serializes this tool, not Settings. Use a configuration change
    window; rechecks detect intervening edits but cannot make native writes atomic.
    """
    state = journal.read()
    objects = validate(package)
    fresh, actual, identities = inspection(native, package, state)
    if state.get('status') in {'applying', 'failed'}:
        raise ConfigurationError('An incomplete promotion requires reconciliation; inspect status before retrying')
    verify_plan(plan, fresh)
    native.preflight(objects, identities)
    if all(op['decision'] == 'unchanged' for op in fresh['operations']):
        return state
    state = {**state, 'status': 'applying', 'plan': deepcopy(plan),
             'package_checksum': digest(package), 'completed': [], 'pending': None}
    journal.save(state)
    expected = deepcopy(actual)
    try:
        for obj in objects:
            key = obj['key']
            if expected.get(key) == obj:
                # No write and no dependency repin is needed. Final verification
                # checks these again; avoid an O(n^2) API scan for pure adoption.
                state['completed'].append(key)
                continue
            observed, identities = native.snapshot(objects)
            # Recheck ALL resources before every write, not only the current one.
            if observed != expected:
                raise ConfigurationError('Destination configuration changed during promotion')
            resolved = resolve(obj['payload'], identities)
            current_raw, identity = native.read(obj)
            # Compare resolved pins. A changed dependency must repin consumers even
            # when the package's logical reference did not change.
            if current_raw != resolved:
                state['pending'] = {'key': key, 'before': digest(current_raw)}
                journal.save(state)  # intent is durable before an external write
                def checkpoint(data):
                    state['pending'].update(data)
                    journal.save(state)
                native.write(obj, resolved, identity, checkpoint)
                observed, identities = native.snapshot(objects)
                verified, _ = native.read(obj)
                if verified != resolve(obj['payload'], identities):
                    raise ConfigurationError(f'Native read-back did not match the release: {key}')
                # Only the operated resource may have changed. A dependency's old
                # pins can temporarily stop normalizing; preserve their raw IDs
                # by recording the fresh snapshot but verify at final completion.
                for other in observed:
                    if other != key and other in expected and observed[other] != expected[other]:
                        # Reference changes are allowed only for version IDs of the
                        # object just written; other edits must stop the release.
                        before = expected[other]
                        after = observed[other]
                        from .configuration_package import walk, reference
                        old_version = identity.get('version_id')
                        def normalize_old(v):
                            return reference(key, 'version_id') if old_version and v == old_version else v
                        normalized = {**after, 'payload': walk(after['payload'], normalize_old)}
                        if normalized != before:
                            raise ConfigurationError('Unrelated configuration changed during a write')
                expected = observed
            state['completed'].append(key)
            state['pending'] = None
            journal.save(state)
        # Resolve every pin against final identities; do not call an old pinned
        # workflow synchronized merely because logical object names match.
        actual, identities = native.snapshot(objects)
        for obj in objects:
            value, _ = native.read(obj)
            if value != resolve(obj['payload'], identities):
                raise ConfigurationError(f'Final configuration verification failed: {obj["key"]}')
        state.update(status='applied', baseline={o['key']: o for o in objects}, pending=None,
                     verified_at=datetime.now(timezone.utc).isoformat(),
                     bindings={o['key']: identities[o['key']]['id'] for o in objects if o['kind'] == 'method'})
        journal.save(state)
        return state
    except Exception:
        state['status'] = 'failed'
        # Never persist upstream exception text: API errors can contain values.
        journal.save(state)
        raise


def reconcile(native, package, journal):
    """Recover a fully applied release after a response/checkpoint failure.

    Partial native writes are not replayed automatically. This operation succeeds
    only if EVERY destination value and pin already equals the intended package.
    """
    state = journal.read()
    if state.get('status') not in {'failed', 'applying'} or state.get('package_checksum') != digest(package):
        raise ConfigurationError('No matching interrupted promotion to reconcile')
    objects = validate(package)
    _, identities = native.snapshot(objects)
    for obj in objects:
        raw, _ = native.read(obj)
        if raw != resolve(obj['payload'], identities):
            raise ConfigurationError('Promotion is partial; repair through reviewed native Settings before reconciliation')
    state.update(status='applied', baseline={o['key']: o for o in objects}, pending=None,
                 verified_at=datetime.now(timezone.utc).isoformat(),
                 bindings={o['key']: identities[o['key']]['id'] for o in objects if o['kind'] == 'method'})
    journal.save(state)
    return state


def release_status(dsn, organization):
    """Read journal metadata only. No native API calls and no implied live drift check."""
    with psycopg.connect(dsn) as db:
        if db.execute("SELECT to_regclass('hrms_configuration_releases')").fetchone()[0] is None:
            return []
        rows = db.execute('SELECT package_name, state FROM hrms_configuration_releases WHERE organization_id=%s ORDER BY package_name',
                          (organization,)).fetchall()
        return [{'name': name, 'status': state['status'], 'checksum': state.get('package_checksum'),
                 'verified_at': state.get('verified_at'), 'pending': (state.get('pending') or {}).get('key')}
                for name, state in rows]
