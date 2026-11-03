"""Assignment eligibility from native transition grants and lifecycle form bindings."""
import os
from .errors import AppError


def bound_state(workflow, state, variable):
    identity = os.getenv(variable)
    return bool(identity) and any(s['name'] == state and any(
        r['method_id'] == identity for r in s.get('method_refs', []))
        for s in workflow['definition'].get('states', []))


def cancelled(workflow, state):
    return bound_state(workflow, state, 'HRMS_EMPLOYEE_CANCELLED_FORM_ID')


def cancellation(workflow, transition):
    return cancelled(workflow, transition.get('to_state'))


def payroll_step(workflow, state):
    return bound_state(workflow, state, 'HRMS_EMPLOYEE_PAYROLL_FORM_ID')


def managed(workflow):
    return any(payroll_step(workflow, s['name']) for s in workflow['definition'].get('states', []))


def state_tags(workflow, state):
    return set(next((s.get('tags', []) for s in workflow['definition'].get('states', []) if s['name'] == state), []))


def fixed_user(workflow, state, record):
    from .employee_work import is_employee_profile_step, is_owner_signoff_step
    if is_employee_profile_step(workflow, state):
        return record.get('data', {}).get('platform_user_id')
    if is_owner_signoff_step(workflow, state):
        return record.get('owner_id')
    return None


def context(platform, actor, entity_id, workflow_id):
    from .employee_work import employee_enrollments
    enrollment = next((e for e in employee_enrollments(platform, actor)
                       if e['entity_id'] == entity_id and e['workflow_id'] == workflow_id), None)
    if not enrollment:
        raise AppError(404, 'Onboarding record is not available')
    record = platform.request('GET', '/entity-records/' + entity_id, token=actor.token)
    workflow = platform.request('GET', '/workflow-state-machines/' + workflow_id, token=actor.token)
    if record['organization_id'] != actor.organization_id:
        raise AppError(403, 'Employee organization mismatch')
    return record, workflow, enrollment['current_state']


def assignees(platform, actor, entity_id, workflow_id):
    record, workflow, state = context(platform, actor, entity_id, workflow_id)
    tags = state_tags(workflow, state)
    if not actor.roles & {'hrms_hr_full', 'superadmin'}:
        raise AppError(403, 'HR Full or Super Admin must manage onboarding assignments')
    if 'terminal' in tags:
        return {'items': [], 'current': record.get('assignee_id'), 'fixed': True}
    if not managed(workflow):
        return {'items': [], 'current': record.get('assignee_id'), 'fixed': True, 'unsupported': True}
    from .onboarding_account_link import approval_step
    fixed = fixed_user(workflow, state, record)
    from .employee_work import is_employee_profile_step, is_owner_signoff_step
    is_fixed = is_employee_profile_step(workflow, state) or is_owner_signoff_step(workflow, state)
    outgoing = {t['key'] for t in workflow['definition']['transitions']
                if t.get('from') == state and not cancellation(workflow, t)}
    items = []
    for user in platform.users():
        if user.get('organization_id') != actor.organization_id or user.get('status') != 'active':
            continue
        if user.get('email') == platform.email:
            continue
        memberships = platform.call('GET', f"/roles/users/{user['id']}/roles")
        roles = set()
        grants = set()
        for membership in memberships:
            if membership['organization_id'] != actor.organization_id:
                raise AppError(403, 'Role organization mismatch')
            role = platform.call('GET', '/roles/' + membership['role_id'])
            if role['organization_id'] != actor.organization_id:
                raise AppError(403, 'Role organization mismatch')
            roles.add(role['name'])
            grants.update((g['machine_name'], g['transition_key']) for g in role.get('transition_permissions', []))
        if is_fixed and user['id'] != fixed:
            continue
        admin_step = approval_step(workflow, state) or payroll_step(workflow, state)
        if admin_step and 'superadmin' not in roles:
            continue
        if not admin_step and roles == {'superadmin'} and not is_fixed:
            continue
        if not (admin_step or is_fixed) and not any((workflow['machine_name'], k) in grants for k in outgoing):
            continue
        items.append({'id': user['id'], 'name': user.get('full_name') or user['email']})
    return {'items': items, 'current': record.get('assignee_id'), 'fixed': is_fixed}


def assign(platform, actor, entity_id, workflow_id, user_id):
    options = assignees(platform, actor, entity_id, workflow_id)
    if user_id not in {u['id'] for u in options['items']}:
        raise AppError(422, 'Choose an active assignee authorized for this onboarding stage')
    return platform.request('PUT', f'/entity-records/{entity_id}/assignee', token=actor.token,
                            json={'assignee_id': user_id})
