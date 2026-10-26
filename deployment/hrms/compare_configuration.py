"""Read native definitions only; no journal, installer, or promotion writes."""
import json
import os
import sys
from collections import Counter

from hrms_app.configuration_native import NativeConfiguration
from hrms_app.configuration_package import ConfigurationError, validate
from hrms_app.configuration_promotion import inspection
from hrms_app.platform import PlatformClient


class ReadOnlyPlatform(PlatformClient):
    def request(self, method, path, **kwargs):
        if method != 'GET' and (method, path) != ('POST', '/auth/login'):
            raise RuntimeError('Configuration comparison cannot write native data')
        return super().request(method, path, **kwargs)


def main():
    package = json.load(sys.stdin)
    validate(package)
    api = ReadOnlyPlatform(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                           os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        api.service_token()
        plan, actual, _ = inspection(NativeConfiguration(api), package, {'baseline': {}})
        desired = {item['key']: item for item in package['objects']}
        differences = [{'key': op['key'], 'production': actual.get(op['key']),
                        'desired': desired[op['key']]} for op in plan['operations']
                       if op['decision'] == 'conflict']
        print(json.dumps({'comparison': 'initial adoption; no baseline modified',
                          'summary': dict(Counter(item['decision'] for item in plan['operations'])),
                          'plan': plan, 'differences': differences}, indent=2))
    except ConfigurationError as exc:
        print(json.dumps({'blocked': True, 'reason': str(exc)}))
        raise SystemExit(2) from None
    except Exception:
        print(json.dumps({'blocked': True, 'reason': 'Native configuration could not be read; check access and deployed adapter compatibility.'}))
        raise SystemExit(2) from None
    finally:
        api.close()


if __name__ == '__main__':
    main()
