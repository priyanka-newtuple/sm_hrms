from pathlib import Path


def test_platform_container_runs_one_server_without_development_reloader():
    root = Path(__file__).resolve().parents[3]
    dockerfile = root / 'applications/hrms_api/platform.Dockerfile'
    if not dockerfile.exists():
        import pytest
        pytest.skip('Repository Dockerfile is not mounted')
    command = next(line for line in dockerfile.read_text().splitlines() if line.startswith('CMD '))
    assert 'alembic -c' in command
    assert '&& exec python -m uvicorn main:app' in command
    assert 'python main.py' not in command
    assert '--reload' not in command
