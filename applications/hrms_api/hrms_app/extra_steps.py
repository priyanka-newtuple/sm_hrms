"""Steps an organization adds to an HRMS workflow in Settings → Funnels.

HRMS runs the steps it owns with its own rules (who approves, date checks, and so on). A step
an organization adds, or any step out of a state it added, has no HRMS rule, so it is offered as
a plain button to the people who manage that kind of record, and run as it is configured.
"""
from .catalog import PACKS, pack_by_type
from .cockpit_catalog import TYPES as COCKPIT_TYPES
from .errors import AppError
from .policy import capabilities
from .workflow_config import step_targets

LEAVE = 'HRMS.LeaveRequest'
# Who may run added steps on each kind of record.
MANAGERS = {
    LEAVE: 'onboarding:manage',  # HR, as well as the leave's own approvers
    'HRMS.OnboardingCase': 'onboarding:manage', 'HRMS.OnboardingStep': 'onboarding:manage',
    **{kind: 'performance:manage' for kind in ('HRMS.PerformanceCycle', 'HRMS.PerformanceReview',
                                                'HRMS.PerformanceGoal', 'HRMS.ProjectFeedback')},
    **{kind: 'cockpit:publish' for kind in COCKPIT_TYPES},
    'HRMS.WorkFromHomeRequest': 'wfh:approve', 'HRMS.WorkFromHomePolicy': 'wfh:configure',
}


def hrms_step(entity_type, state, transition):
    """A transition HRMS itself runs from this state, under its own trigger or a renamed one."""
    owned = {name for source, name, _ in pack_by_type(entity_type).transitions if source == state}
    return transition['trigger'] in owned or any(
        transition['to_state'] in step_targets(entity_type, state, name) for name in owned)


class ExtraSteps:
    def __init__(self, service):
        self.service, self.platform, self.journal = service, service.platform, service.journal

    def _record(self, actor, entity_id):
        record = self.platform.record(entity_id)
        types = {t['entity_type_id']: t['name'] for t in self.platform.call('GET', '/entity-types')['items']
                 if t.get('name') in MANAGERS and any(p.entity_type == t['name'] for p in PACKS)}
        kind = types.get(record['entity_type_id'])
        if kind is None:
            raise AppError(404, 'This record has no HRMS workflow')
        allowed = MANAGERS[kind] in capabilities(actor)
        if not allowed and kind == LEAVE:
            from .service import LeaveApprovers
            employees = self.service.employees()
            employee = next((e for e in employees if e['entity_id'] == record['data'].get('employee_id')), None)
            allowed = bool(employee) and actor.user_id in LeaveApprovers(self.platform, employees)(
                employee, record['data'].get('start_date', ''), record['data'].get('end_date', ''))
        return kind, allowed

    def available(self, actor, entity_id):
        kind, allowed = self._record(actor, entity_id)
        if not allowed:
            return {'current_state': None, 'steps': []}
        available = self.platform.call('GET', f'/entities/{entity_id}/transitions/available')
        state = available.get('current_state')
        return {'current_state': state, 'steps': [
            {'trigger': t['trigger'], 'label': t.get('label') or t['trigger'].replace('_', ' ').capitalize(),
             'to_state': t['to_state']}
            for t in available.get('available_transitions', [])
            if t.get('allowed', True) and not hrms_step(kind, state, t)]}

    def run(self, actor, entity_id, trigger, idempotency_key):
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(db, actor, f'extra-step:{idempotency_key}', {'entity_id': entity_id, 'trigger': trigger})
            if op.result:
                return op.result
            if trigger not in {s['trigger'] for s in self.available(actor, entity_id)['steps']}:
                raise AppError(403, 'This step is not available to you now')
            self.platform.call('POST', f'/entities/{entity_id}/transitions', json={
                'entity_id': entity_id, 'trigger': trigger, 'idempotency_key': f'hrms:extra:{idempotency_key}',
                'inputs': {'hrms_actor_id': actor.user_id}})
            self.journal.audit(db, actor, f'workflow.step:{trigger}', entity_id)
            result = {'entity_id': entity_id, 'trigger': trigger}
            op.finish(result)
            return result
