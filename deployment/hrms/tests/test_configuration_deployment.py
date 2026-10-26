from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_managed_configuration_has_one_writer_and_precedes_workers():
    script = (ROOT / 'deploy.sh').read_text(encoding='utf-8')
    start = script.index('if [[ -f "$release/configuration.json" ]]')
    end = script.index('\nfi', start)
    managed, legacy = script[start:end].split('\nelse\n')
    assert 'hrms_app.configuration_cli deploy' in managed
    assert 'platform-install < /dev/null' not in managed
    assert 'platform-install < /dev/null' in legacy
    assert 'not automatically synchronized' in legacy
    assert end < script.index('up -d --no-deps platform-worker')
    assert ':ro" platform-install' in managed


def test_deployment_does_not_reset_runtime_data():
    script = (ROOT / 'deploy.sh').read_text(encoding='utf-8')
    assert 'pg_dump' in script
    for forbidden in ('pg_restore', 'drop database', 'down -v', 'volume rm', 'volume prune'):
        assert forbidden not in script.lower()
