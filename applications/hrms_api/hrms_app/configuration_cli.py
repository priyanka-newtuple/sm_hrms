"""Server-side configuration release commands. Credentials come only from env."""
import argparse
import json
import os
from pathlib import Path

from .configuration_native import NativeConfiguration, export_package
from .configuration_package import ConfigurationError, digest, validate
from .configuration_promotion import Journal, apply, inspection, reconcile
from .platform import PlatformClient


def read_json(filename):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ConfigurationError('Duplicate JSON property')
            result[key] = value
        return result
    return json.loads(Path(filename).read_text(encoding='utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ConfigurationError('Invalid JSON number')))


def output(value, filename=None):
    content = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    if filename:
        target = Path(filename)
        # A failed export must not destroy the previous approved package.
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(target)
    else:
        print(content, end='')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'export', 'plan', 'apply', 'reconcile', 'status', 'deploy'])
    parser.add_argument('--package')
    parser.add_argument('--plan')
    parser.add_argument('--output')
    parser.add_argument('--entity', action='append', default=[])
    parser.add_argument('--role', action='append', default=[], help='Explicit roles whose scoped workflow/entity grants should be exported')
    parser.add_argument('--name', default='hrms-core')
    parser.add_argument('--bindings', help='Destination-only package-key to native method ID mappings')
    parser.add_argument('--write-bindings', help='Export source method mappings separately; do not commit these as destination mappings')
    args = parser.parse_args(argv)
    package = read_json(args.package) if args.package else None
    if args.command not in {'export', 'status'} and not package:
        parser.error('--package is required')
    if package:
        validate(package)
    if args.command == 'validate':
        output({'valid': True, 'checksum': digest(package), 'objects': len(package['objects'])}, args.output)
        return
    if args.command == 'export' and not args.entity:
        parser.error('Export requires explicit --entity selections')
    if args.command == 'apply' and not args.plan:
        parser.error('Apply requires a reviewed --plan file')
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        api.service_token()  # validates tenant even if there are no objects to read
        native = NativeConfiguration(api, read_json(args.bindings) if args.bindings else None)
        if args.command == 'export':
            output(export_package(native, args.entity, args.name, args.role), args.output)
            if args.write_bindings:
                output(native.bindings, args.write_bindings)
            return
        journal = Journal(os.environ['HRMS_APP_DATABASE_URL'], api.org, package['name'] if package else args.name)
        with journal.locked():
            state = journal.read()
            native.bindings = {**state.get('bindings', {}), **native.bindings}
            if args.command == 'status':
                output({'organization': api.org, 'package_name': args.name,
                        'status': state['status'], 'checksum': state.get('package_checksum'),
                        'completed': state.get('completed', []), 'pending': state.get('pending')}, args.output)
                return
            if args.command == 'plan':
                result, _, _ = inspection(native, package, state)
                output(result, args.output)
                if result['blocked']:
                    raise ConfigurationError('Configuration conflicts require review; no native changes made')
                return
            if args.command == 'reconcile':
                state = reconcile(native, package, journal)
            elif args.command == 'deploy':
                # First adoption is always a separate reviewed operation. Once
                # adopted, main's package is the reviewed desired release.
                if state['status'] != 'applied' or not state.get('baseline'):
                    raise ConfigurationError('Initial configuration adoption is required before managed deployment')
                plan, _, _ = inspection(native, package, state)
                state = apply(native, package, plan, journal)
            else:
                state = apply(native, package, read_json(args.plan), journal)
            output({'status': state['status'], 'checksum': state.get('package_checksum')}, args.output)
    finally:
        api.close()


if __name__ == '__main__':
    try:
        main()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        # Do not leak upstream response bodies or environment credentials into CI.
        raise SystemExit('Configuration operation failed; inspect the tenant configuration and promotion status') from None
