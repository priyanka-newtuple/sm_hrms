from contextlib import contextmanager
from copy import deepcopy
import pytest
from hrms_app.errors import AppError
from hrms_app.offboarding_notifications import dispatch, event_stage, definition, TAG


class Journal:
    def __init__(self): self.ops = {}
    @contextmanager
    def lock(self, org): yield None
    def operation(self, db, actor, key, payload):
        class Op:
            result = None
            def __init__(self): self.progress = {}
            def checkpoint(self, **values): self.progress.update(deepcopy(values))
            def finish(self, value): self.result = value
        return self.ops.setdefault((actor.organization_id, key), Op())


class Platform:
    org = 'org'
    def __init__(self): self.rows = []; self.enrolled = set(); self.lose_create_response = False
    def records(self, *args): return deepcopy(self.rows)
    def call(self, method, path, **kwargs):
        if path.startswith('/entity-types/'): return {'entity_type_id': 'notice'}
        if path == '/entity-records':
            row = {'entity_id': str(len(self.rows)), 'data': deepcopy(kwargs['json']['data'])}
            self.rows.append(row)
            if self.lose_create_response:
                self.lose_create_response = False
                raise AppError(503, 'Response lost after commit')
            return row
        if path.endswith('/with-states'):
            return {'states': [{'workflow_id': 'notice-workflow'}] if path.split('/')[2] in self.enrolled else []}
        if path.endswith('/enrollments'):
            self.enrolled.add(kwargs['json']['entity_id']); return {}
        raise AssertionError(path)


def inputs():
    return ({'id': 'event1', 'organization_id': 'org', 'event_type': 'TRANSITION_SUCCEEDED', 'after_state': 'Submitted'},
            {'entity_id': 'exit1', 'organization_id': 'org', 'data': {'employee_notification_email': 'employee@example.test',
             'offboarding_coordinator_email': 'hr@example.test', 'offboarding_workspace_url': 'https://myhub.example/hrms/my-work', 'exit_employee_code': 'EMP-1'}},
            {'definition': {'initial_state': 'Not Started', 'states': [{'description': TAG}]}},
            {'id': 'notice-workflow', 'machine_name': 'notices'}, {'Exit checklist v2 · Submitted': 'template1'})


def test_rapid_events_queue_independent_notices_and_retries_do_not_duplicate():
    p, j = Platform(), Journal()
    for index in range(5):
        args = list(inputs()); args[0]['id'] = str(index)
        dispatch(p, j, *args); dispatch(p, j, *args)
    assert len(p.rows) == len(p.enrolled) == 10
    assert {r['data']['recipient'] for r in p.rows} == {'employee@example.test', 'hr@example.test'}
    assert all(set(r['data']) == {'notice_key','recipient','template_id','workspace_url','employee_code','source_entity_id','source_event_id','stage'} for r in p.rows)


def test_recovers_lost_create_response_without_duplicate():
    p, j = Platform(), Journal(); p.lose_create_response = True
    with pytest.raises(AppError): dispatch(p, j, *inputs())
    dispatch(p, j, *inputs())
    assert len(p.rows) == len(p.enrolled) == 2


def test_cross_tenant_rejected_before_writes():
    p, j = Platform(), Journal(); args = list(inputs()); args[1]['organization_id'] = 'other'
    with pytest.raises(AppError): dispatch(p, j, *args)
    assert not p.rows


def test_old_workflows_and_idempotent_transition_replays_are_ignored():
    event, source, workflow, _, _ = inputs()
    event['metadata'] = {'outputs': {'idempotent': True}}
    assert event_stage(event, workflow) is None
    event['metadata'] = {}; workflow['definition']['states'] = []
    assert event_stage(event, workflow) is None


def test_native_delivery_has_one_action_and_completion_only_after_send():
    graph = definition()
    action = graph['states'][0]['on_state_actions'][0]
    assert len(graph['states'][0]['on_state_actions']) == 1
    assert action['kind'] == 'mail.send_email'
    assert action['outcome_triggers'] == {'sent': 'sent'}
    assert graph['transitions'][0]['to_state'] == 'Delivered'


def test_missing_routing_does_not_create_or_mark_sent():
    p, j = Platform(), Journal(); args = list(inputs())
    args[1]['data']['employee_notification_email'] = ''
    with pytest.raises(AppError): dispatch(p, j, *args)
    assert not p.rows and not p.enrolled


def test_reconcile_cursor_retries_failed_scan_and_deduplicates(monkeypatch):
    from hrms_app import offboarding_notifications as module
    event, source, workflow, notice, templates = inputs()
    event.update(entity_type='HRMS.Offboarding', entity_id='exit1', event_timestamp='2026-10-29T00:00:00Z', metadata={'workflow_id':'exit-workflow'})
    notice.update(entity_type=module.ENTITY, is_active=True)
    class ScanPlatform(Platform):
        fail = True
        def record(self, eid): return source
        def call(self, method, path, **kwargs):
            if path == '/workflow-state-machines': return {'published_items':[notice]}
            if path == '/email-templates': return {'items':[{'name':k,'template_id':v} for k,v in templates.items()]}
            if path == '/audit-events':
                if self.fail: raise AppError(503,'Audit unavailable')
                return {'items':[event] if kwargs['params']['event_type']=='TRANSITION_SUCCEEDED' else [], 'total':1 if kwargs['params']['event_type']=='TRANSITION_SUCCEEDED' else 0}
            if path == '/workflow-state-machines/exit-workflow': return workflow
            return super().call(method,path,**kwargs)
    p,j = ScanPlatform(),Journal()
    with pytest.raises(AppError): module.reconcile(p,j)
    cursor=j.ops[('org','exit-notification-cursor-v1')]
    assert 'through' not in cursor.progress
    p.fail=False
    module.reconcile(p,j); module.reconcile(p,j)
    assert cursor.progress['through']
    assert len(p.rows)==2
