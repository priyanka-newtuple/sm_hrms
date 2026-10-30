"""Read native definitions only; no journal, installer, or promotion writes."""
import json
import os
import sys
import httpx
from collections import Counter

from hrms_app.configuration_native import NativeConfiguration
from hrms_app.configuration_package import ConfigurationError, validate, resolve, digest
from hrms_app.configuration_promotion import inspection
from hrms_app.platform import PlatformClient


class ReadOnlyPlatform(PlatformClient):
    def request(self, method, path, **kwargs):
        if method != 'GET' and (method, path) not in {('POST', '/auth/login'), ('POST', '/workflow-state-machines/validate')}:
            raise RuntimeError('Configuration comparison cannot write native data')
        return super().request(method, path, **kwargs)


class InspectedConfiguration(NativeConfiguration):
    current_key = None
    last_route = None

    def read(self, obj):
        self.current_key = obj['key']
        return super().read(obj)

    def get(self, route, **kwargs):
        self.last_route = route
        return super().get(route, **kwargs)


def main():
    package = json.load(sys.stdin)
    validate(package)
    api = ReadOnlyPlatform(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                           os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    api.http.timeout = httpx.Timeout(120)
    try:
        api.service_token()
        native = InspectedConfiguration(api)
        # Read only our own journal; validation is a native non-mutating endpoint.
        import psycopg
        with psycopg.connect(os.environ['HRMS_APP_DATABASE_URL']) as db:
            row = db.execute('SELECT state FROM hrms_configuration_releases WHERE organization_id=%s AND package_name=%s',
                             (api.org, package['name'])).fetchone()
        state = row[0] if row else {'baseline': {}}
        native.bindings = state.get('bindings', {})
        plan, actual, identities = inspection(native, package, state)
        preflight_error = None
        try:
            native.preflight(validate(package), identities)
        except ConfigurationError as exc:
            preflight_error = {'reason': str(exc), 'object': native.current_key}
        draft_review = None
        if preflight_error and preflight_error['reason'] == 'Existing workflow draft must be resolved before promotion':
            target = next(o for o in package['objects'] if o['key'] == preflight_error['object'])
            _, identity = native.read(target)
            published = native.get('/workflow-state-machines/' + identity['id'])
            drafts = native.get('/workflow-state-machines', params={'scope':'draft','machine_name':identity['machine_name']})['draft_items']
            draft_review = []
            for summary in drafts:
                draft = native.get('/workflow-state-machines/' + summary['id'])
                def canonical(graph):
                    from copy import deepcopy
                    graph = deepcopy(graph)
                    for transition in graph.get('transitions', []):
                        if 'from_state' in transition:
                            transition['from'] = transition.pop('from_state')
                    return graph
                left, right = canonical(draft['definition']), canonical(published['definition'])
                draft_review.append({'id': draft['id'], 'canonical_matches_published': left == right,
                                     'differences': {k: {'draft':left.get(k),'published':right.get(k)} for k in set(left)|set(right) if left.get(k)!=right.get(k)}, 'definition_matches_published': draft['definition'] == published['definition'],
                                     'canvas_matches_published': draft.get('canvas_metadata') == published.get('canvas_metadata')})
        workflow_validation = {}
        for item in validate(package):
            if item['kind'] != 'workflow' or not identities.get(item['key']):
                continue
            try:
                graph = resolve(item['payload'], identities)['definition']
            except ConfigurationError:
                continue  # New method dependencies are not created by comparison.
            identity = identities[item['key']]
            graph['machine_key'] = identity['machine_name']
            workflow_validation[item['key']] = api.call('POST', '/workflow-state-machines/validate',
                json={'machine_name': identity['machine_name'], 'definition': graph})
        pending = state.get('pending')
        diagnostic = None
        if pending and pending.get('draft_id'):
            draft = native.get('/workflow-state-machines/' + pending['draft_id'])
            item = next(o for o in package['objects'] if o['key'] == pending['key'])
            graph = resolve(item['payload'], identities)['definition']
            graph['machine_key'] = pending['machine_name']
            diagnostic = {'pending': pending, 'draft_checksum': digest(draft), 'draft_version': draft.get('version'),
                          'validation': api.call('POST', '/workflow-state-machines/validate',
                                                json={'machine_name': pending['machine_name'], 'definition': graph})}
        desired = {item['key']: item for item in package['objects']}
        differences = [{'key': op['key'], 'production': actual.get(op['key']),
                        'desired': desired[op['key']]} for op in plan['operations']
                       if op['decision'] == 'conflict']
        role_diagnostics = []
        for summary in api.call('GET', '/roles'):
            if summary['name'] not in {'hrms_hr_full', 'hrms_application_service'}:
                continue
            role = api.call('GET', '/roles/' + summary['id'])
            role_diagnostics.append({
                'name': role['name'],
                'permissions': [p['permission_key'] for p in role['permissions']],
                'entity_permissions': [p for p in role['entity_permissions'] if p['entity_type'] == 'HRMS.Offboarding'],
                'workflow_permissions': role['workflow_permissions'],
            })
        print(json.dumps({'comparison': 'read-only comparison; no baseline modified',
                          'role_diagnostics': role_diagnostics,
                          'summary': dict(Counter(item['decision'] for item in plan['operations'])),
                          'plan': plan, 'differences': differences, 'pending_diagnostic': diagnostic, 'preflight_error': preflight_error, 'draft_review': draft_review, 'workflow_validation': workflow_validation}, indent=2))
    except ConfigurationError as exc:
        print(json.dumps({'blocked': True, 'reason': str(exc)}))
        raise SystemExit(2) from None
    except Exception as exc:
        import traceback
        print(json.dumps({'blocked': True, 'reason': 'Native configuration could not be read; check access and deployed adapter compatibility.',
                          'error_type': type(exc).__name__, 'cause_type': type(exc.__cause__).__name__, 'status': getattr(exc, 'status', None),
                          'object': getattr(locals().get('native'), 'current_key', None),
                          'route': getattr(locals().get('native'), 'last_route', None),
                          'frames': [{'file': f.filename.rsplit('/', 1)[-1], 'line': f.lineno, 'function': f.name}
                                     for f in traceback.extract_tb(exc.__traceback__)[-5:]]}))
        raise SystemExit(2) from None
    finally:
        api.close()


if __name__ == '__main__':
    main()
