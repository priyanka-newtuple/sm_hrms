from copy import deepcopy

import pytest

from hrms_app.configure_email import configure, smtp_payload


VALUES = dict(EMAIL_ENABLED='true', SMTP_HOST='smtp.gmail.com', SMTP_PORT='587',
              SMTP_USERNAME='sender@example.com', EMAIL_FROM='Newtuple HRMS <sender@example.com>',
              SMTP_PASSWORD='example-test-password')


def test_display_sender_is_parsed_and_credentials_are_not_in_config():
    payload = smtp_payload(VALUES)
    assert payload['config']['from_email'] == 'sender@example.com'
    assert payload['config']['from_name'] == 'Newtuple HRMS'
    assert payload['config']['smtp_use_tls'] is True
    assert payload['secrets'] == {'username': 'sender@example.com', 'password': 'example-test-password'}
    assert 'password' not in str(payload['config'])


@pytest.mark.parametrize('patch', [{'SMTP_PASSWORD': ''}, {'SMTP_PORT': '25'}, {'EMAIL_ENABLED': 'maybe'},
                                  {'EMAIL_FROM': 'invalid'}, {'EMAIL_FROM': 'sender@example.com\nBcc: other@example.com'}])
def test_invalid_secrets_fail_before_api_access(patch):
    with pytest.raises(ValueError):
        smtp_payload({**VALUES, **patch})


def test_disabled_sync_preserves_settings_without_calls():
    assert configure(object(), smtp_payload({'EMAIL_ENABLED': 'false'})) is False


class Api:
    org = 'tenant'

    def __init__(self, valid=True):
        self.valid = valid
        self.calls = []

    def service_token(self):
        self.calls.append('authenticated')

    def call(self, method, path, **kwargs):
        self.calls.append((method, path, deepcopy(kwargs['json'])))
        return {'valid': self.valid} if method == 'POST' else {'organization_id': self.org, 'configured': True}


def test_configuration_uses_tenant_api_and_validates_without_sending_email():
    api = Api()
    assert configure(api, smtp_payload(VALUES))
    assert api.calls[0] == 'authenticated'
    assert api.calls[1][0:2] == ('POST', '/integrations/organizations/tenant/smtp/validate')
    assert api.calls[2][0:2] == ('PUT', '/integrations/organizations/tenant/smtp')
    assert len(api.calls) == 3


def test_invalid_credentials_do_not_replace_working_configuration():
    api = Api(False)
    with pytest.raises(RuntimeError):
        configure(api, smtp_payload(VALUES))
    assert len(api.calls) == 2
