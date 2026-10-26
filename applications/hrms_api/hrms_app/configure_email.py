"""Deploy SMTP tenant configuration through public APIs, reading secrets on stdin."""
import json
import os
import sys
from email.utils import parseaddr

from pydantic import EmailStr, TypeAdapter

from .platform import PlatformClient
from .errors import AppError


def smtp_payload(values):
    enabled = str(values.get('EMAIL_ENABLED', '')).strip().lower()
    if enabled in {'', 'false', '0', 'no'}:
        return None
    if enabled not in {'true', '1', 'yes'}:
        raise ValueError('EMAIL_ENABLED must be true or false')
    required = ('EMAIL_FROM', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USERNAME', 'SMTP_PASSWORD')
    if any(not str(values.get(key, '')).strip() for key in required):
        raise ValueError('Missing email deployment secrets')
    port = int(values['SMTP_PORT'])
    if port not in {465, 587}:
        raise ValueError('Use SMTP port 465 or 587 with TLS')
    sender = values['EMAIL_FROM'].strip()
    if '\n' in sender or '\r' in sender:
        raise ValueError('Invalid sender header')
    display_name, address = parseaddr(sender)
    address = str(TypeAdapter(EmailStr).validate_python(address))
    return {
        'display_name': 'HRMS email', 'validate': True, 'set_default': True,
        'config': {'smtp_host': values['SMTP_HOST'].strip(), 'smtp_port': port,
                   'smtp_use_tls': True, 'from_email': address,
                   'from_name': display_name or 'Newtuple HRMS'},
        'secrets': {'username': values['SMTP_USERNAME'].strip(), 'password': values['SMTP_PASSWORD']},
    }


def deployment_payload(values):
    """UAT captures by default; real delivery requires an explicit live selection."""
    mode = str(values.get('HRMS_EMAIL_MODE') or 'capture').strip().lower()
    if mode == 'capture':
        return {
            'display_name': 'UAT inbox — captured, not delivered',
            'validate': True, 'set_default': True,
            'config': {'smtp_host': 'mailpit', 'smtp_port': 1025,
                       'smtp_use_tls': False, 'from_email': 'myhub@newtuple.com',
                       'from_name': 'MyHub UAT'},
            'secrets': {'username': 'uat', 'password': 'capture'},
        }
    if mode != 'live':
        raise ValueError('HRMS_EMAIL_MODE must be capture or live')
    payload = smtp_payload(values)
    if payload is None:
        raise ValueError('Live mode requires EMAIL_ENABLED and complete SMTP credentials')
    if payload['config']['smtp_host'].lower() in {'mailpit', 'local-mail', 'localhost', '127.0.0.1'}:
        raise ValueError('Live mode requires the real SMTP provider')
    return payload


class EmailConfigurationError(RuntimeError):
    """Only constant, credential-free diagnostics may be included here."""


def configure(api, payload):
    if payload is None:
        return False
    # service_token verifies that installer credentials authenticate in the expected tenant.
    try:
        api.service_token()
    except AppError as exc:
        raise EmailConfigurationError(f'Installer authentication failed (HTTP {exc.status}).') from None
    path = f'/integrations/organizations/{api.org}/smtp'
    try:
        validation = api.call('POST', path + '/validate', json={
            'config': payload['config'], 'secrets': payload['secrets']})
    except AppError as exc:
        raise EmailConfigurationError(f'SMTP validation API failed (HTTP {exc.status}).') from None
    if not validation.get('valid'):
        raise EmailConfigurationError('SMTP validation rejected the connection. Check Mailpit reachability in capture mode or provider credentials in live mode.')
    try:
        result = api.call('PUT', path, json=payload)
    except AppError as exc:
        raise EmailConfigurationError(f'Saving SMTP integration failed (HTTP {exc.status}).') from None
    if result.get('organization_id') != api.org or not result.get('configured'):
        raise EmailConfigurationError('SMTP configuration was not confirmed in the expected tenant.')
    return True


def main():
    api = None
    try:
        try:
            values = json.load(sys.stdin)
            if not isinstance(values, dict):
                raise ValueError()
        except (ValueError, TypeError):
            raise EmailConfigurationError('Email deployment input is missing or invalid JSON. Redeploy from the release pipeline.') from None
        try:
            payload = deployment_payload(values)
        except (ValueError, TypeError):
            raise EmailConfigurationError('Email mode or SMTP settings are invalid. Capture mode needs no live SMTP secrets; live mode requires complete TLS SMTP settings.') from None
        if payload is None:
            print('Email secret synchronization skipped; existing email settings are unchanged.')
            return 0
        api = PlatformClient(os.environ['PLATFORM_API_URL'], os.environ['HRMS_ORGANIZATION_ID'],
                             os.environ['HRMS_INSTALL_EMAIL'], os.environ['HRMS_INSTALL_PASSWORD'])
        configure(api, payload)
        print('Email mode configured and SMTP validated. No email was sent by configuration.')
        return 0
    except EmailConfigurationError as exc:
        print(f'Email configuration failed: {exc}', file=sys.stderr)
        return 1
    except Exception:
        # Upstream validation errors may contain credential fragments; do not echo them in CI.
        print('Email configuration failed. Check email secrets and SMTP authentication in Settings.', file=sys.stderr)
        return 1
    finally:
        if api is not None:
            api.close()


if __name__ == '__main__':
    sys.exit(main())
