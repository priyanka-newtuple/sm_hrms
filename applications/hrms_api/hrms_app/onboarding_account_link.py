"""Explicit, authorized reconciliation of an employee with an existing native user."""
import os

from .errors import AppError
from .platform import Actor
from .policy import capabilities, require


def approval_step(workflow, state):
    method = os.getenv('HRMS_EMPLOYEE_APPROVAL_FORM_ID')
    return bool(method and any(
        s['name'] == state and any(r['method_id'] == method for r in s.get('method_refs', []))
        for s in workflow['definition']['states']))


def candidate(platform, actor, record):
    if 'employee:activate' not in capabilities(actor):
        return None
    if record['organization_id'] != actor.organization_id:
        raise AppError(403, 'Employee organization mismatch')
    data = record['data']
    if data.get('platform_user_id'):
        return None
    email = str(data.get('work_email') or '').strip().lower()
    users = [u for u in platform.users() if u.get('organization_id') == actor.organization_id
             and str(u.get('email') or '').strip().lower() == email]
    if len(users) != 1:
        return None
    user = users[0]
    return {'user_id': user['id'], 'email': user['email'], 'active': user['status'] == 'active'}


def link(service, actor, entity_id, workflow_id, user_id):
    from .employee_work import employee_work
    require(actor, 'employee:activate')
    p = service.platform
    with service.journal.lock(actor.organization_id) as db:
        item = next((i for i in employee_work(p, actor)
                     if i['entity_id'] == entity_id and i['workflow_id'] == workflow_id), None)
        workflow = p.request('GET', '/workflow-state-machines/' + workflow_id, token=actor.token)
        if not item or not item['actions'] or not approval_step(workflow, item['current_state']):
            raise AppError(409, 'Open the current Account Approval task before linking an account')
        record = p.request('GET', '/entity-records/' + entity_id, token=actor.token)
        if record['data'].get('employment_status') in {'inactive', 'offboarded'}:
            raise AppError(409, 'An employee who has left cannot be linked through onboarding')
        match = candidate(p, actor, record)
        bridge_actor = Actor('hrms-account-bridge', p.org, '', frozenset(), frozenset())
        op = service.journal.operation(db, bridge_actor, 'employee-account:' + entity_id, {'entity_id': entity_id})
        retry = (record['data'].get('platform_user_id') == user_id
                 and op.progress.get('existing_account_id') == user_id)
        if not retry and (not match or match['user_id'] != user_id or not match['active']):
            raise AppError(409, 'The matching account must be active and unchanged before linking')
        if op.progress.get('created_user_id') or op.progress.get('create_requested'):
            raise AppError(409, 'Account creation is already in progress; administrator review is required')
        others = p.records('HRMS.Employee', ['platform_user_id'])
        if any(r['entity_id'] != entity_id and r['data'].get('platform_user_id') == user_id for r in others):
            raise AppError(409, 'This account is already linked to another employee')
        # Persist preservation intent before the link: a worker retry must never change this user's role.
        if op.progress.get('existing_account_id') not in (None, user_id):
            raise AppError(409, 'A different account link is already being reconciled')
        op.checkpoint(existing_account_id=user_id)
        p.call('PUT', '/entity-records/' + entity_id, json={'data': {'platform_user_id': user_id}})
        service.journal.audit(db, actor, 'employee.onboarding.existing_account_linked', entity_id)
        return {'linked': True}
