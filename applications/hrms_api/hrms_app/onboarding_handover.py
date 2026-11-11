"""Recoverable handover using the human's native transition and assignment APIs."""
from .errors import AppError
from . import onboarding_routing as routing


def transition_with_handover(platform, actor, entity_id, workflow_id, trigger,
                            idempotency_key, journal, next_assignee_id=None):
    from .employee_work import transition_employee
    payload = dict(entity_id=entity_id, workflow_id=workflow_id, trigger=trigger,
                   next_assignee_id=next_assignee_id)
    # A cached response must not restore access after the caller loses visibility.
    routing.context(platform, actor, entity_id, workflow_id)
    with journal.lock(actor.organization_id) as db:
        op = journal.operation(db, actor, 'onboarding-handover:' + idempotency_key, payload)
        if op.result is not None:
            return op.result
        if not op.progress:
            options = routing.assignees(platform, actor, entity_id, workflow_id, trigger)
            if options.get('unsupported'):
                raise AppError(409, 'Assignment rules are not configured for this workflow')
            terminal = options.get('terminal', False)
            # Profile completion goes to the employee, whose login the transition creates.
            employee = options.get('employee_account', False)
            if not terminal and not employee and (not options.get('can_assign') or
                    next_assignee_id not in {u['id'] for u in options['items']}):
                raise AppError(422, 'Select an eligible assignee for the next stage')
            _, _, source = routing.context(platform, actor, entity_id, workflow_id)
            op.checkpoint(source=source, target=options.get('state'), terminal=terminal, employee=employee)
        # Retrying the same native idempotency key recovers a lost HTTP response.
        if 'transition' not in op.progress:
            _, _, state = routing.context(platform, actor, entity_id, workflow_id)
            if state == op.progress['source']:
                result = transition_employee(platform, actor, entity_id, workflow_id, trigger,
                                             idempotency_key, journal=journal, _db=db)
            elif state == op.progress['target']:
                # Native idempotency is the authority for a response lost after commit.
                result = platform.request('POST', f'/entities/{entity_id}/transitions',
                    token=actor.token, json=dict(entity_id=entity_id, workflow_id=workflow_id,
                                               trigger=trigger, idempotency_key=idempotency_key))
            else:
                raise AppError(409, 'The record has moved again. Review the current workflow.')
            op.checkpoint(transition=result)
        if not op.progress['terminal']:
            _, _, state = routing.context(platform, actor, entity_id, workflow_id)
            if state != op.progress['target']:
                raise AppError(409, 'The record has moved again. Review its current assignment before continuing.')
            # Revalidate membership and native permission, including on retry.
            try:
                if op.progress.get('employee'):
                    # Same service assignment the account worker keeps in place for this step.
                    user_id = platform.record(entity_id)['data'].get('platform_user_id')
                    if not user_id:
                        raise AppError(409, 'The employee login is not linked yet')
                    platform.call('PUT', f'/entity-records/{entity_id}/assignee', json={'assignee_id': user_id})
                else:
                    routing.assign(platform, actor, entity_id, workflow_id, next_assignee_id)
            except AppError as exc:
                raise AppError(503, 'The stage moved, but its assignment could not be confirmed. Retry the same handover.') from exc
        result = op.progress['transition']
        op.finish(result)
        return result
