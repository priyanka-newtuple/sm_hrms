from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_capture_inbox_is_private_persistent_and_not_a_relay():
    compose = yaml.safe_load((ROOT / 'compose.yml').read_text(encoding='utf-8'))
    inbox = compose['services']['mailpit']
    assert inbox['ports'] == ['127.0.0.1:${HRMS_MAILPIT_PORT:-18025}:8025']
    assert inbox['volumes'] == ['mailpit_data:/data']
    assert inbox['environment']['MP_DATABASE'] == '/data/mailpit.db'
    assert not any('RELAY' in k or 'FORWARD' in k for k in inbox['environment'])


def test_transport_configured_before_worker_starts():
    script = (ROOT / 'deploy.sh').read_text()
    assert script.index('stop platform-worker') < script.index('hrms_app.configure_email')
    assert script.index('hrms_app.configure_email') < script.index('up -d --no-deps platform-worker')
    assert 'platform-install < /dev/null' in script
