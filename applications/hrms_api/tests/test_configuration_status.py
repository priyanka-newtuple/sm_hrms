from types import SimpleNamespace

from fastapi.testclient import TestClient

from hrms_app.main import create_app
from hrms_app.platform import Actor
from native_permissions import grants


def test_release_metadata_requires_configuration_admin_and_uses_actor_tenant(monkeypatch):
    calls = []

    class Platform:
        org = 'tenant-a'

        def records(self, *args):
            return []

        def actor(self, token):
            return Actor(token, self.org, token, frozenset({token}), grants({token}))

    def status(dsn, organization):
        calls.append((dsn, organization))
        return []

    monkeypatch.setattr('hrms_app.configuration_promotion.release_status', status)
    client = TestClient(create_app(Platform(), SimpleNamespace(dsn='application-db')))
    denied = client.get('/v1/api/hrms/configuration-release', headers={'Authorization': 'Bearer hrms_employee'})
    assert denied.status_code == 403
    assert calls == []
    allowed = client.get('/v1/api/hrms/configuration-release?organization_id=other',
                         headers={'Authorization': 'Bearer superadmin'})
    assert allowed.status_code == 200
    assert calls == [('application-db', 'tenant-a')]
    assert allowed.json()['live_drift_checked'] is False
