"""Durable native notification records, independent of the exit's action chain.

Only public platform APIs are used. The HRMS journal coordinates retry-safe
creation; the native mail executor owns delivery and the configured transport.
"""
from datetime import datetime, timezone, timedelta
import hashlib

from .errors import AppError
from .platform import Actor
from .offboarding_checklist import staged_forms

ENTITY = 'HRMS.OffboardingNotice'
TAG = 'hrms:durable-exit-notifications'
FIELDS = [dict(field=k, type='string', required=True) for k in (
    'notice_key', 'recipient', 'template_id', 'workspace_url', 'employee_code',
    'source_entity_id', 'source_event_id', 'stage',
)]


def definition():
    return dict(machine_key='hrms_offboarding_notice', name='Offboarding notifications',
                entity_type=ENTITY, entity_schema={'entity_type': ENTITY, 'fields': FIELDS},
                initial_state='Queued', transitions=[{'key': 'sent', 'trigger': 'sent', 'label': 'Email delivered', 'from': 'Queued', 'to_state': 'Delivered'}], states=[{
                    'name': 'Queued', 'order': 1, 'tags': ['initial'],
                    'on_state_actions': [{'kind': 'mail.send_email', 'outcome_triggers': {'sent': 'sent'}, 'config': {
                        'to': '$entity.recipient', 'template_id': '$entity.template_id',
                        'workspace_url': '$entity.workspace_url', 'employee_code': '$entity.employee_code',
                    }}],
                }, {'name': 'Delivered', 'order': 2, 'tags': ['terminal'], 'on_state_actions': []}])


def event_stage(event, workflow):
    """Only opted-in, committed native transitions create notifications."""
    graph = workflow['definition']
    if not any(TAG in (s.get('description') or '') for s in graph['states']):
        return None
    if event['event_type'] == 'ENTITY_ENROLLED':
        return graph['initial_state']
    if event['event_type'] == 'TRANSITION_SUCCEEDED':
        # Replaying an idempotent transition must not produce another notice.
        if event.get('metadata', {}).get('outputs', {}).get('idempotent'):
            return None
        return event.get('after_state')
    return None


def dispatch(platform, journal, event, source, workflow, notice_workflow, templates):
    stage = event_stage(event, workflow)
    if not stage:
        return
    if event.get('organization_id') != platform.org or source['organization_id'] != platform.org:
        raise AppError(403, 'Notification tenant mismatch')
    template = templates.get('Exit checklist v2 · ' + stage)
    if not template:
        raise AppError(409, 'Configure the native exit stage email template')
    values = source['data']
    actor = Actor('hrms-notifications', platform.org, '', frozenset(), frozenset())
    with journal.lock(platform.org + ':exit-notifications') as db:
        for field in ('employee_notification_email', 'offboarding_coordinator_email'):
            key = hashlib.sha256((event['id'] + ':' + field).encode()).hexdigest()
            op = journal.operation(db, actor, 'exit-notice:' + key, {'event': event['id'], 'recipient_field': field})
            if op.result:
                continue
            if not op.progress.get('envelope'):
                recipient = values.get(field)
                if field == 'employee_notification_email' and staged_forms(workflow):
                    if values.get('notification_email_confirmed') != 'Yes' or not recipient:
                        user = next((u for u in platform.users() if u['id'] == values.get('offboarding_employee_user_id')), None)
                        recipient = user.get('email') if user else None
                envelope = dict(notice_key=key, recipient=recipient, template_id=template,
                                workspace_url=values.get('offboarding_workspace_url'),
                                employee_code=values.get('exit_employee_code'), source_entity_id=source['entity_id'],
                                source_event_id=event['id'], stage=stage)
                if not all(envelope.values()):
                    raise AppError(409, 'Offboarding notification routing is incomplete')
                op.checkpoint(envelope=envelope)
            if not op.progress.get('entity_id'):
                # Recover a lost create response before attempting any new write.
                rows = platform.records(ENTITY, ['notice_key'])
                matches = [r for r in rows if r['data'].get('notice_key') == key]
                if len(matches) > 1:
                    raise AppError(409, 'Duplicate notification records require reconciliation')
                if matches:
                    op.checkpoint(entity_id=matches[0]['entity_id'])
                elif op.progress.get('create_requested'):
                    raise AppError(409, 'Notification creation outcome requires reconciliation')
                else:
                    kind = platform.call('GET', '/entity-types/' + ENTITY)
                    op.checkpoint(create_requested=True)
                    record = platform.call('POST', '/entity-records', json={
                        'entity_type_id': kind['entity_type_id'], 'data': op.progress['envelope']})
                    op.checkpoint(entity_id=record['entity_id'])
            eid = op.progress['entity_id']
            states = platform.call('GET', '/entity-records/' + eid + '/with-states')['states']
            if not states:
                platform.call('POST', '/workflow-state-machines/' + notice_workflow['machine_name'] + '/enrollments',
                              json={'entity_id': eid})
            elif len(states) != 1 or states[0]['workflow_id'] != notice_workflow['id']:
                raise AppError(409, 'Notification workflow enrollment mismatch')
            op.finish({'entity_id': eid, 'queued': True})


def reconcile(platform, journal):
    published = platform.call('GET', '/workflow-state-machines', params={'scope': 'published'})['published_items']
    notices = [w for w in published if w['entity_type'] == ENTITY and w['is_active']]
    if not notices:
        return  # Feature is activated only by its native configuration package.
    if len(notices) != 1:
        raise AppError(409, 'Expected one notification workflow')
    templates = {t['name']: t['template_id'] for t in platform.call('GET', '/email-templates')['items']}
    actor = Actor('hrms-notifications', platform.org, '', frozenset(), frozenset())
    # Cursor advances only after a complete successful scan. One-day overlap
    # covers delayed audit commits; per-event journal keys suppress duplicates.
    with journal.lock(platform.org + ':exit-notification-scan') as db:
        cursor = journal.operation(db, actor, 'exit-notification-cursor-v1', {'version': 1})
        start = cursor.progress.get('through')
        scan_started = datetime.now(timezone.utc).isoformat()
        date_from = (datetime.fromisoformat(start) - timedelta(days=1)).date().isoformat() if start else None
        events = []
        for event_type in ('ENTITY_ENROLLED', 'TRANSITION_SUCCEEDED'):
            offset = 0
            while True:
                params = dict(event_type=event_type, limit=200, offset=offset)
                if date_from:
                    params['date_from'] = date_from
                page = platform.call('GET', '/audit-events', params=params)
                events.extend(e for e in page['items'] if e.get('entity_type') == 'HRMS.Offboarding' and not e.get('entity_archived'))
                offset += len(page['items'])
                if offset >= page['total']:
                    break
                if not page['items']:
                    raise AppError(502, 'Incomplete native audit page')
        workflows, sources = {}, {}
        for event in sorted(events, key=lambda e: (e['event_timestamp'], e['id'])):
            wid = event.get('metadata', {}).get('workflow_id')
            if not wid:
                continue
            if wid not in workflows:
                workflows[wid] = platform.call('GET', '/workflow-state-machines/' + wid)
            if not event_stage(event, workflows[wid]):
                continue
            eid = event['entity_id']
            if eid not in sources:
                sources[eid] = platform.record(eid)
            dispatch(platform, journal, event, sources[eid], workflows[wid], notices[0], templates)
        cursor.checkpoint(through=scan_started)
