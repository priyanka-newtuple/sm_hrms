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
        plan, actual, identities = inspection(native, package, {'baseline': {}})
        # Read only our own journal; validation is a native non-mutating endpoint.
        import psycopg
        with psycopg.connect(os.environ['HRMS_APP_DATABASE_URL']) as db:
            row = db.execute('SELECT state FROM hrms_configuration_releases WHERE organization_id=%s AND package_name=%s',
                             (api.org, package['name'])).fetchone()
        pending = (row[0].get('pending') if row else None)
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
        print(json.dumps({'comparison': 'initial adoption; no baseline modified',
                          'summary': dict(Counter(item['decision'] for item in plan['operations'])),
                          'plan': plan, 'differences': differences, 'pending_diagnostic': diagnostic}, indent=2))
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
