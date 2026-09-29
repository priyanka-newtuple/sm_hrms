import time

import httpx
import pytest

from hrms_app.errors import AppError
from hrms_app.platform import PlatformClient


@pytest.mark.parametrize('recovered', [True, False])
def test_expired_service_session_is_renewed_once_without_expiring_browser(recovered):
    seen = []
    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith('/auth/login'):
            return httpx.Response(200, json={'access_token': 'renewed'})
        if request.url.path.endswith('/roles/my-permissions'):
            return httpx.Response(200, json={'organization_id': 'org'})
        if recovered and request.headers.get('authorization') == 'Bearer renewed':
            return httpx.Response(200, json={'items': []})
        return httpx.Response(401, json={'detail': 'Missing or invalid access token'})
    api = PlatformClient('http://platform/v1/api', 'org', 'service', 'secret', transport=httpx.MockTransport(handler))
    api._token = 'expired'
    api._expires = time.monotonic() + 240
    if recovered:
        assert api.call('GET', '/entity-records/summary') == {'items': []}
    else:
        with pytest.raises(AppError) as error:
            api.call('GET', '/entity-records/summary')
        assert error.value.status == 503
    assert seen.count('/v1/api/auth/login') == 1
    assert seen.count('/v1/api/entity-records/summary') == 2
    api.close()
