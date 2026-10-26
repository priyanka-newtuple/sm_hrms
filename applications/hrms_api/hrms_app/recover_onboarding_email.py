"""Explicit UAT-only recovery through native password setup; never prints mail content."""
import json
import os
import sys
import time

import httpx
import psycopg

from .platform import PlatformClient


class RecoveryBlocked(ValueError):
    """Only fixed, credential-free prerequisite messages."""


def capture_configuration(api):
    items = api.call('GET', f'/integrations/organizations/{api.org}')['items']
    defaults = api.call('GET', f'/integrations/organizations/{api.org}/defaults')
    if defaults.get('organization_id') != api.org or not any(
        d['capability'] == 'communication' and d['provider'] == 'smtp'
        for d in defaults['items']
    ):
        raise RecoveryBlocked('Recovery requires SMTP as the tenant default email provider')
    configured = [i for i in items if i['provider'] == 'smtp' and i.get('configured')]
    if len(configured) != 1:
        raise RecoveryBlocked('Recovery requires a configured SMTP integration')
    config = configured[0].get('config', {})
    if config.get('smtp_host') != 'mailpit' or int(config.get('smtp_port', 0)) != 1025:
        raise RecoveryBlocked('Recovery requires the private Mailpit capture destination')


def recover(api, progress, entity_id, mailbox):
    capture_configuration(api)
    record = api.record(entity_id)
    uid = record.get('data', {}).get('platform_user_id')
    if record['organization_id'] != api.org or not uid or progress.get('created_user_id') != uid:
        raise RecoveryBlocked('Recovery requires an account created and linked by onboarding')
    user = next((u for u in api.users() if u['id'] == uid), None)
    if not user or user['organization_id'] != api.org or user['status'] != 'active' or user.get('auth_type') != 'local':
        raise RecoveryBlocked('Recovery requires an approved local account in this tenant')
    email = record['data'].get('work_email', '').strip().lower()
    if not email or user['email'].lower() != email:
        raise RecoveryBlocked('Linked account email does not match the employee')
    before = mailbox(email)
    api.request('POST', '/auth/forgot-password', json={'email': email})
    for _ in range(10):
        if mailbox(email) - before:
            return {'setup_request_accepted': True, 'new_email_captured': True}
        time.sleep(1)
    return {'setup_request_accepted': True, 'new_email_captured': False}


def employee_id_for_reference(api, employee_ref):
    records = [r for r in api.records('HRMS.Employee', ['identifier'])
               if (r['data'].get('identifier') or r.get('display_name')) == employee_ref]
    if len(records) != 1:
        raise RecoveryBlocked('Employee reference must resolve exactly once in this tenant')
    return records[0]['entity_id']


def main():
    if os.environ.get('HRMS_EMAIL_MODE') != 'capture':
        raise RecoveryBlocked('This recovery is available only in capture mode')
    employee_ref = sys.argv[1]
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'], os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        entity_id = employee_id_for_reference(api, employee_ref)
        with psycopg.connect(os.environ['HRMS_APP_DATABASE_URL']) as db:
            row = db.execute('SELECT progress FROM operations WHERE organization_id=%s AND operation_key=%s', (api.org, 'employee-account:' + entity_id)).fetchone()
        if not row:
            raise RecoveryBlocked('No onboarding account handoff exists for this employee')
        with httpx.Client(base_url='http://mailpit:8025', timeout=15) as client:
            def mailbox(email):
                response = client.get('/api/v1/search', params={'query': 'to:' + email, 'limit': 1000})
                response.raise_for_status()
                return {m['ID'] for m in response.json().get('messages', [])}
            result = recover(api, row[0], entity_id, mailbox)
        print(json.dumps(result))
        return 0 if result['new_email_captured'] else 1
    finally:
        api.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RecoveryBlocked as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('UAT setup-email recovery did not complete; no delivery is confirmed.', file=sys.stderr)
        sys.exit(1)
