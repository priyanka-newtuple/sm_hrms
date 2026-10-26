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


from hrms_app.configure_email import deployment_payload


def test_deployment_defaults_to_capture_even_when_live_secrets_exist():
    payload = deployment_payload(VALUES)
    assert payload['config']['smtp_host'] == 'mailpit'
    assert payload['config']['smtp_port'] == 1025
    assert VALUES['SMTP_PASSWORD'] not in str(payload)
    api = Api()
    assert configure(api, payload)


def test_explicit_live_mode_uses_validated_real_credentials():
    assert deployment_payload({**VALUES, 'HRMS_EMAIL_MODE': 'live'}) == smtp_payload(VALUES)


@pytest.mark.parametrize('values', [
    {'HRMS_EMAIL_MODE': 'invalid'},
    {'HRMS_EMAIL_MODE': 'live'},
    {**VALUES, 'HRMS_EMAIL_MODE': 'live', 'EMAIL_ENABLED': 'false'},
    {**VALUES, 'HRMS_EMAIL_MODE': 'live', 'SMTP_HOST': 'mailpit'},
])
def test_invalid_mode_or_unconfigured_live_fails_closed(values):
    with pytest.raises(ValueError):
        deployment_payload(values)


@pytest.mark.parametrize('raw', ['', 'not-json', '[]'])
def test_missing_or_invalid_pipeline_input_has_safe_diagnostic(monkeypatch, capsys, raw):
    import io
    from hrms_app import configure_email as module
    monkeypatch.setattr(module.sys, 'stdin', io.StringIO(raw))
    monkeypatch.setattr(module, 'PlatformClient', lambda *a: pytest.fail('Must reject before API access'))
    assert module.main() == 1
    assert 'input is missing or invalid JSON' in capsys.readouterr().err


@pytest.mark.parametrize('stage', ['authenticate', 'POST', 'PUT'])
def test_upstream_errors_report_stage_without_credential_text(stage):
    from hrms_app.configure_email import EmailConfigurationError
    from hrms_app.errors import AppError
    class FailingApi(Api):
        def service_token(self):
            if stage=='authenticate': raise AppError(403, 'sensitive-secret-marker')
        def call(self, method, path, **kwargs):
            if method==stage: raise AppError(403, 'sensitive-secret-marker')
            return super().call(method,path,**kwargs)
    with pytest.raises(EmailConfigurationError) as error:
        configure(FailingApi(), deployment_payload({}))
    assert 'HTTP 403' in str(error.value)
    assert 'sensitive-secret-marker' not in str(error.value)
