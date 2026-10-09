import importlib.util
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'configure_google.py'

@pytest.fixture
def configure():
    spec = importlib.util.spec_from_file_location('configure_google', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.configure


def test_google_secret_update_preserves_other_settings(configure, tmp_path):
    path = tmp_path / 'production.env'
    path.write_text('HRMS_PUBLIC_URL=https://hrms.example.com\nGOOGLE_CLIENT_ID=old\n')
    assert configure({'GOOGLE_CLIENT_ID': 'client.apps.googleusercontent.com', 'GOOGLE_CLIENT_SECRET': 'GOCSPX-example'}, path)
    assert 'HRMS_PUBLIC_URL=https://hrms.example.com' in path.read_text()
    assert path.read_text().count('GOOGLE_CLIENT_ID=') == 1
    assert 'GOOGLE_CLIENT_SECRET=GOCSPX-example' in path.read_text()


def test_missing_secrets_preserve_configuration(configure, tmp_path):
    path = tmp_path / 'production.env'
    path.write_text('GOOGLE_CLIENT_ID=old\n')
    assert not configure({}, path)
    assert path.read_text() == 'GOOGLE_CLIENT_ID=old\n'


@pytest.mark.parametrize('secret', ['', 'unsafe\nOTHER=value', '${ENV}'])
def test_partial_or_unsafe_credentials_fail_without_writes(configure, tmp_path, secret):
    path = tmp_path / 'production.env'
    path.write_text('KEEP=value\n')
    with pytest.raises(ValueError):
        configure({'GOOGLE_CLIENT_ID': 'client', 'GOOGLE_CLIENT_SECRET': secret}, path)
    assert path.read_text() == 'KEEP=value\n'
