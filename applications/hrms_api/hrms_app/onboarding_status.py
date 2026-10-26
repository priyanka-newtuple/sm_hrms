"""Read-only operational check; no names, email addresses or message bodies in output."""
import json
import os
from collections import Counter

from .onboarding_bindings import resolve
from .platform import PlatformClient


def main():
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'], os.environ['HRMS_SERVICE_EMAIL'], os.environ['HRMS_SERVICE_PASSWORD'])
    try:
        bindings = resolve(api)
        users = {u['id']: u for u in api.users()}
        records = api.records('HRMS.Employee', ['identifier', 'platform_user_id'])
        linked = [r['data'].get('platform_user_id') for r in records if r['data'].get('platform_user_id')]
        print(json.dumps({'onboarding_forms_resolved': len(bindings), 'linked_employee_accounts': len(linked), 'linked_account_statuses': dict(Counter(users.get(uid, {}).get('status', 'missing') for uid in linked)), 'pending_tenant_users': sum(u['status'] == 'pending' for u in users.values()), 'restricted_onboarding_role_exists': any(r['name'] == 'hrms_onboarding_employee' for r in api.call('GET', '/roles'))}))
    finally:
        api.close()


if __name__ == '__main__':
    main()
