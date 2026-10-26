import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('uat_switches', ROOT / 'configure_uat_inbox.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_switches_fail_closed_and_live_always_disables():
    assert module.switches({}) == ('capture', 'false')
    assert module.switches({'HRMS_UAT_INBOX_ENABLED': 'true'}) == ('capture', 'true')
    assert module.switches({'HRMS_UAT_INBOX_ENABLED': 'true', 'HRMS_EMAIL_MODE': 'live'}) == ('live', 'false')
    with pytest.raises(ValueError):
        module.switches({'HRMS_UAT_INBOX_ENABLED': 'typo'})


def test_disable_applies_before_live_transport_and_no_public_mailpit():
    script = (ROOT / 'deploy.sh').read_text()
    assert script.index('configure_uat_inbox.py') < script.index('export HRMS_EMAIL_MODE HRMS_UAT_INBOX_ENABLED')
    assert script.index('up -d --no-deps --wait --wait-timeout 180 hrms-app') < script.index('hrms_app.configure_email')
    assert '127.0.0.1:${HRMS_MAILPIT_PORT:-18025}:8025' in (ROOT / 'compose.yml').read_text()
