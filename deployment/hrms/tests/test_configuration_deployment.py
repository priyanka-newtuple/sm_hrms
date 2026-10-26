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


def test_initial_adoption_requires_review_and_backups():
    roots = [parent for parent in ROOT.parents if (parent / '.github').is_dir()]
    if not roots:
        import pytest
        pytest.skip('Repository workflow is not mounted in the deployment-only test container')
    workflow = (roots[0] / '.github/workflows/hrms-configuration-adoption.yml').read_text()
    assert 'workflow_dispatch:' in workflow and '\n  push:' not in workflow
    assert 'group: hrms-production' in workflow
    assert 'reviewed/comparison.json' in workflow
    assert "run['headSha'] == os.environ['RELEASE_SHA']" in workflow
    assert 'flock -n 9' in workflow
    assert workflow.index('pg_dump') < workflow.index("shlex.quote(payload)")
    for forbidden in ('pg_restore', 'down -v', 'volume rm', 'volume prune'):
        assert forbidden not in workflow
