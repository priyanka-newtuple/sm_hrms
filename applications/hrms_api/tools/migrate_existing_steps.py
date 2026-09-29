"""One-time, read-only export of pre-boundary tasks; target writes use public APIs.

This utility is deliberately outside the running HRMS package/image. The old
task API cannot read these rows because its permission keys are unregistered.
Original completion timestamps are provenance; new transition events describe
this migration, not a historical approval by the original employee.
"""
import os

import psycopg
from psycopg.rows import dict_row

from hrms_app.platform import PlatformClient


def main():
    org = os.environ['HRMS_ORGANIZATION_ID']
    api = PlatformClient(os.environ['PLATFORM_API_URL'], org,
                         os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
    with psycopg.connect(os.environ['HRMS_STEP_SOURCE_DATABASE_URL'], row_factory=dict_row) as db:
        db.execute('SET TRANSACTION READ ONLY')
        rows = db.execute('''SELECT id, entity_id, stage, title, description, assigned_to,
                                    due_date, completed_at, status
                             FROM modular_backend.tasks
                             WHERE organization_id=%s AND entity_type='HRMS.OnboardingCase'
                               AND archived_at IS NULL AND stage LIKE 'onboarding-step-%%'
                             ORDER BY entity_id, stage''', (org,)).fetchall()
    existing = api.records('HRMS.OnboardingStep', ['legacy_task_id', 'case_id', 'sequence'])
    by_legacy = {r['data'].get('legacy_task_id'): r for r in existing}
    created = 0
    for row in rows:
        step = by_legacy.get(row['id'])
        if step is None:
            step = api.create_record('HRMS.OnboardingStep', {
            'case_id': row['entity_id'], 'sequence': int(row['stage'].rsplit('-', 1)[1]),
            'title': row['title'], 'description': row['description'], 'assigned_to': row['assigned_to'],
            'due_date': row['due_date'].isoformat() if row['due_date'] else None,
            'legacy_task_id': row['id'],
            'legacy_completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
            }, None)
            created += 1
        state = api.enroll(step['entity_id'], 'hrms_onboardingstep')
        if state == 'open' and row['status'] in {'COMPLETED', 'CANCELLED'}:
            api.call('POST', f"/entities/{step['entity_id']}/transitions", json={
                'entity_id': step['entity_id'], 'trigger': 'complete' if row['status'] == 'COMPLETED' else 'cancel',
                'idempotency_key': f"hrms-step-migration:{row['id']}",
                'inputs': {'migration_source_task_id': row['id']}})
    after = api.records('HRMS.OnboardingStep', ['legacy_task_id', 'case_id', 'sequence'])
    migrated = {r['data'].get('legacy_task_id') for r in after}
    assert {r['id'] for r in rows} <= migrated, 'Not all original steps were migrated'
    print(f'Onboarding step migration: source={len(rows)} created={created} preserved={len(rows)-created}')
    api.close()


if __name__ == '__main__':
    main()
