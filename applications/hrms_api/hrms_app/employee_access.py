"""Narrow HR account onboarding actions over public platform APIs."""
import os
from urllib.parse import urlsplit

from .errors import AppError
from .policy import require


def identity_roles(platform, actor, identity):
    rows = platform.call('GET', f"/roles/users/{identity['id']}/roles")
    if any(r['organization_id'] != actor.organization_id for r in rows):
        raise AppError(403, 'Account roles belong to another organization')
    return {r['role_name'] for r in rows}


def setup_access(service, actor, employee_id, operation_key):
    require(actor, 'employee:activate')
    local_email_disabled = (os.getenv('HRMS_LOCAL_DISABLE_EMAIL', '').lower() == 'true'
                            and os.getenv('HRMS_ORGANIZATION_ID') == '11111111-1111-1111-1111-111111111111'
                            and os.getenv('PLATFORM_API_URL') == 'http://platform-api:8000/v1/api')
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
        if not roles:
            raise AppError(403, 'Account must have a native role before activation')
        if identity['status'] not in {'pending', 'active'}:
            raise AppError(409, 'Suspended or rejected accounts require administrator review')
        if op.result:
            return {**op.result, 'idempotent': True}
        google = identity.get('auth_type') == 'google' or google_sign_in_ready(service, identity['email'])
        # Check configuration before granting access. Never return secrets to the browser.
        if not google and not local_email_disabled:
            integrations = service.platform.call('GET', f'/integrations/organizations/{actor.organization_id}')
            if integrations.get('organization_id') != actor.organization_id:
                raise AppError(403, 'Email configuration belongs to another organization')
            if not any(i.get('configured') and i['provider'] in {
                    'smtp', 'ses', 'azure_communication', 'microsoft_graph_email'} for i in integrations['items']):
                raise AppError(409, 'Ask Super Admin to configure and test an email provider in Settings → Integrations first')
        if identity['status'] == 'pending':
            op.checkpoint(activation_requested=True, original_roles=sorted(roles))
            service.journal.audit(db, actor, 'employee.access.activation_requested', employee_id)
            service.platform.request('POST', f'/users/{user_id}/approve', token=actor.token)
        if op.progress.get('activation_requested'):
            # Native approval may add viewer. Preserve the explicitly authorized roles.
            assigned = service.platform.call('GET', f'/roles/users/{user_id}/roles')
            for role in assigned:
                if role['role_name'] == 'viewer' and 'viewer' not in roles:
                    service.platform.call('DELETE', f"/roles/users/{user_id}/roles/{role['role_id']}")
        if local_email_disabled:
            message = 'Account active. Setup email is disabled for local testing; no password setup link was sent.'
            email_status = 'disabled_local'
        elif google:
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


def google_sign_in_ready(service, email):
    """Whether this work email can sign in with Google here, so no password-setup email is needed.

    Google sign-in links an existing account by email on first use. It is ready only when the HRMS
    callback is HTTPS (the browser flow refuses anything else), the platform has Google configured,
    and the address is on the organization's work domain.
    """
    redirect = urlsplit(os.environ.get('GOOGLE_REDIRECT_URI', ''))
    if redirect.scheme != 'https' or not redirect.hostname:
        return False
    if not email.casefold().endswith('@' + service.domain.casefold()):
        return False
    response = service.platform.http.get('auth/google/url', params={'redirect_uri': redirect.geturl()})
    return response.status_code == 200
