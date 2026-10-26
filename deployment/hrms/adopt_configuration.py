"""Apply a repository-reviewed initial adoption through native public APIs."""
import json
import os
import sys

from hrms_app.configuration_native import NativeConfiguration
from hrms_app.configuration_package import ConfigurationError
from hrms_app.configuration_promotion import Journal, adopt_reviewed, inspection
from hrms_app.platform import PlatformClient


def main():
    inputs = json.load(sys.stdin)
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        api.service_token()
        package = inputs['package']
        native = NativeConfiguration(api)
        journal = Journal(os.environ['HRMS_APP_DATABASE_URL'], api.org, package['name'])
        with journal.locked():
            state = adopt_reviewed(native, package, inputs['review'], journal)
            plan, _, _ = inspection(native, package, state)
            if any(op['decision'] != 'unchanged' for op in plan['operations']):
                raise ConfigurationError('Post-adoption verification detected drift')
            print(json.dumps({'status': state['status'], 'checksum': state['package_checksum'],
                              'verified_objects': len(plan['operations'])}))
    except ConfigurationError as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc)}))
        raise SystemExit(2) from None
    except Exception:
        print(json.dumps({'status': 'failed', 'reason': 'Inspect the promotion journal before retrying; no automatic replay.'}))
        raise SystemExit(2) from None
    finally:
        api.close()


if __name__ == '__main__':
    main()
