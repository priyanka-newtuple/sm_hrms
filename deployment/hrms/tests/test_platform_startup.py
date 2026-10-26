from pathlib import Path


def test_platform_container_runs_one_server_without_development_reloader():
    candidates = [Path('/platform.Dockerfile'), *(parent / 'applications/hrms_api/platform.Dockerfile'
                   for parent in Path(__file__).resolve().parents)]
    dockerfile = next((path for path in candidates if path.is_file()), None)
    assert dockerfile is not None, 'Mount the platform Dockerfile to verify production startup'
    command = next(line for line in dockerfile.read_text().splitlines() if line.startswith('CMD '))
    assert 'alembic -c' in command
    assert '&& exec python -m uvicorn main:app' in command
    assert 'python main.py' not in command
    assert '--reload' not in command
