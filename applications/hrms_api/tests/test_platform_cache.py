from native_permissions import grants
from types import SimpleNamespace

import httpx
import pytest

from hrms_app import platform as platform_module
from hrms_app.cockpit import CockpitService
from hrms_app.errors import AppError
from hrms_app.platform import Actor, PlatformClient

LISTING = [
    {'entity_type': 'HRMS.LeaveRequest', 'is_active': True, 'machine_name': 'workflow_leave'},
    {'entity_type': 'HRMS.LeaveRequest', 'is_active': False, 'machine_name': 'workflow_leave_old'},
    {'entity_type': 'HRMS.Policy', 'is_active': True, 'machine_name': 'workflow_policy'},
]


def client(listing=LISTING):
    c = PlatformClient('http://platform.test', 'org', 'svc@example.com', 'secret',
                       transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    calls = []

    def call(method, path, **kwargs):
        calls.append(path)
        return {'published_items': listing}

    c.call = call
    return c, calls


def test_one_published_listing_resolves_every_type():
    c, calls = client()
    assert c.machine_name('hrms_leaverequest') == 'workflow_leave'
    assert c.machine_name('hrms_policy') == 'workflow_policy'
    assert c.machine_name('hrms_leaverequest') == 'workflow_leave'
    assert calls == ['/workflow-state-machines']


def test_the_listing_is_refreshed_after_its_time_to_live():
    c, calls = client()
    c.machine_name('hrms_policy')
    c._machines_at -= platform_module.MACHINE_NAME_TTL_SECONDS + 1
    c.machine_name('hrms_policy')
    assert len(calls) == 2


def test_a_type_without_one_active_workflow_is_refused_and_not_cached():
    c, calls = client([w for w in LISTING if w['entity_type'] != 'HRMS.Policy'])
    for _ in range(2):
        with pytest.raises(AppError) as error:
            c.machine_name('hrms_policy')
        assert error.value.status == 409
    assert len(calls) == 2  # the failed lookup did not keep serving the bad listing


def test_names_that_are_not_hrms_types_pass_through():
    c, calls = client()
    assert c.machine_name('workflow_custom') == 'workflow_custom' and calls == []


def test_cockpit_approvers_are_unchanged_by_concurrent_role_lookups():
    users = [dict(id=f'u{i}', full_name=f'User {i}', status='active', email=f'u{i}@example.com') for i in range(12)]
    users += [dict(id='off', full_name='Inactive', status='suspended', email='off@example.com'),
              dict(id='svc', full_name='Service', status='active', email='svc@example.com')]
    roles = {u['id']: 'hrms_hr_full' if int(u['id'][1:]) % 3 == 0 else 'hrms_employee' for u in users[:12]}
    platform = SimpleNamespace(email='svc@example.com', users=lambda: users,
                               user_capabilities=lambda user: {'cockpit:approve'} if roles[user] == 'hrms_hr_full' else set(),
                               call=lambda method, path, **kw: [dict(role_name=roles[path.split('/')[3]], organization_id='org')])
    approvers = CockpitService(platform, None).people(Actor('u3', 'org', 'human', frozenset({'hrms_hr_full'}), grants({'hrms_hr_full'})))
    assert approvers == [{'id': f'u{i}', 'name': f'User {i}'} for i in (0, 6, 9)]  # u3 is the actor
