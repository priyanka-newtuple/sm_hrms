"""Narrow HR account onboarding actions over public platform APIs."""
from .errors import AppError
from .policy import capabilities, require


def identity_roles(platform, actor, identity):
    rows = platform.call('GET', f"/roles/users/{identity['id']}/roles")
    if any(r['organization_id'] != actor.organization_id for r in rows):
        raise AppError(403, 'Account roles belong to another organization')
    return {r['role_name'] for r in rows}


def may_manage(actor, roles):
    return ('employee:activate' in capabilities(actor) and bool(roles)
            and (roles <= {'hrms_employee'} or 'platform:configure' in capabilities(actor)))


def setup_access(service, actor, employee_id, operation_key):
    require(actor, 'employee:activate')
    with service.journal.lock(actor.organization_id) as db:
        rows = service.employees()
        employee = next((r for r in rows if r['entity_id'] == employee_id), None)
        if not employee:
            raise AppError(404, 'Employee was not found')
        data = employee['data']
        if data.get('employment_status') != 'active':
            raise AppError(409, 'Only active employees can receive account access')
        user_id = data.get('platform_user_id')
        identity = next((u for u in service.platform.users() if u['id'] == user_id), None)
        if (not identity or identity.get('organization_id') != actor.organization_id
                or identity['email'].casefold() != data['work_email'].casefold()
                or sum(r['data'].get('platform_user_id') == user_id for r in rows) != 1):
            raise AppError(409, 'Employee account link needs administrator reconciliation')
        op = service.journal.operation(db, actor, f'employee-access:{operation_key}', {'employee_id': employee_id})
        roles = identity_roles(service.platform, actor, identity)
        if op.progress.get('activation_requested') and 'viewer' not in op.progress['original_roles']:
            roles.discard('viewer')
        if not may_manage(actor, roles):
            raise AppError(403, 'Only Super Admin can activate or send setup for privileged accounts')
        if identity['status'] not in {'pending', 'active'}:
            raise AppError(409, 'Suspended or rejected accounts require administrator review')
        if op.result:
            return {**op.result, 'idempotent': True}
        # Check configuration before granting access. Never return secrets to the browser.
        if identity.get('auth_type') != 'google':
            integrations = service.platform.call('GET', f'/integrations/organizations/{actor.organization_id}')
            if integrations.get('organization_id') != actor.organization_id:
                raise AppError(403, 'Email configuration belongs to another organization')
            if not any(i.get('configured') and i['provider'] in {
                    'smtp', 'ses', 'azure_communication', 'microsoft_graph_email'} for i in integrations['items']):
                raise AppError(409, 'Ask Super Admin to configure and test an email provider in Settings → Integrations first')
        if identity['status'] == 'pending':
            op.checkpoint(activation_requested=True, original_roles=sorted(roles))
            service.journal.audit(db, actor, 'employee.access.activation_requested', employee_id)
            service.platform.call('POST', f'/users/{user_id}/approve')
        if op.progress.get('activation_requested'):
            # Native approval may add viewer. Preserve the explicitly authorized roles.
            assigned = service.platform.call('GET', f'/roles/users/{user_id}/roles')
            for role in assigned:
                if role['role_name'] == 'viewer' and 'viewer' not in roles:
                    service.platform.call('DELETE', f"/roles/users/{user_id}/roles/{role['role_id']}")
        if identity.get('auth_type') == 'google':
            message = 'Account active. The employee can sign in using Google.'
            email_status = 'not_required'
        else:
            if op.progress.get('setup_requested'):
                raise AppError(409, 'Account is active, but the previous email outcome is unknown. Check the inbox before requesting another setup email.')
            # Checkpoint before sending: a timeout must not produce duplicate mail on retry.
            op.checkpoint(setup_requested=True)
            service.platform.request('POST', '/auth/forgot-password', json={'email': identity['email']})
            message = ('Account active. Password setup email requested. The platform does not confirm delivery; '
                       'if it does not arrive, check email settings and request setup again.')
            email_status = 'requested'
        result = {'account_status': 'active', 'email_status': email_status, 'message': message}
        service.journal.audit(db, actor, 'employee.access.setup_requested', employee_id)
        op.finish(result)
        return result
