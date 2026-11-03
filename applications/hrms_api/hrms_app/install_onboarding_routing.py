"""One-time native transition grants for the revised onboarding workflow.

Later tenant edits are preserved. No users, login settings or runtime records change.
"""
import os
import psycopg
from .errors import AppError
from .onboarding_bindings import initialize
from .onboarding_routing import managed
from .platform import PlatformClient


def grants_for(role, transitions):
    permitted = {
        'hrms_hr_full': {'employee registration __to__email setup', 'email setup__to__profile completion pending',
                         'verification_to_provisioning', 'request_profile_changes', 'hr_signoff_to_completed'},
        'hrms_office_admin': {'email setup__to__profile completion pending', 'provisioning_to_hr_signoff'},
        'hrms_onboarding_employee': {'profile_to_verification'},
    }[role]
    return {t['key'] for t in transitions if t['key'] in permitted or (
        role == 'hrms_hr_full' and t['key'].startswith('cancel_onboarding_'))}


def install(api, dsn):
    initialize(api)
    workflows = api.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items']
    workflows = [w for w in workflows if w['entity_type'] == 'HRMS.Employee' and w['is_active'] and managed(w)]
    if not workflows:
        return
    if len(workflows) != 1:
        raise AppError(409, 'Configure one active payroll-enabled onboarding workflow')
    workflow = workflows[0]
    feature = 'onboarding-payroll-routing-v1'
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS hrms_feature_setup (organization_id text, feature text, PRIMARY KEY (organization_id, feature))')
        if db.execute('SELECT 1 FROM hrms_feature_setup WHERE organization_id=%s AND feature=%s', (api.org, feature)).fetchone():
            return
        for summary in api.call('GET', '/roles'):
            if summary['name'] not in {'hrms_office_admin', 'hrms_onboarding_employee'}:
                continue
            role = api.call('GET', '/roles/' + summary['id'])
            if role['organization_id'] != api.org:
                raise AppError(403, 'Role organization mismatch')
            machine = workflow['machine_name']
            transitions = workflow['definition']['transitions']
            keys = {t['key'] for t in transitions}
            grants = [g for g in role.get('transition_permissions', [])
                      if g['machine_name'] != machine or g['transition_key'] not in keys]
            grants += [{'machine_name': machine, 'transition_key': k}
                       for k in sorted(grants_for(role['name'], transitions))]
            access = list(role.get('workflow_permissions', []))
            if not any(g['machine_name'] == machine for g in access):
                access.append({'machine_name': machine})
            api.call('PUT', '/roles/' + role['id'], json={'workflow_permissions': access, 'transition_permissions': grants})
        db.execute('INSERT INTO hrms_feature_setup VALUES (%s,%s) ON CONFLICT DO NOTHING', (api.org, feature))


if __name__ == '__main__':
    api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    try:
        install(api, os.environ['HRMS_APP_DATABASE_URL'])
    finally:
        api.close()
