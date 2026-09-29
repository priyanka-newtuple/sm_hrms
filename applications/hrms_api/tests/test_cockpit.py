from dataclasses import replace
from uuid import uuid4

import pytest
from hrms_app.cockpit import CockpitService, Command
from hrms_app.errors import AppError
from hrms_app.policy import capabilities
from test_performance import Journal, Platform, actor


@pytest.fixture
def system():
    p, j = Platform(), Journal()
    p.email = "service@test.local"
    p.users = lambda: [
        {"id": "author", "full_name": "Author", "status": "active"},
        {"id": "approver", "full_name": "Approver", "status": "active"},
    ]
    from hrms_app.catalog import pack_by_type

    native = p.call

    def call(method, path, **kwargs):
        if method == "GET" and path == "/forms/config":
            pack = pack_by_type(kwargs["params"]["entity_type"])
            return {"items": [pack.form_request()]}
        return native(method, path, **kwargs)

    p.call = call
    service = CockpitService(p, j)
    service.people = lambda who: (
        [{"id": "approver", "name": "Approver"}]
        if who.user_id != "approver"
        else [{"id": "author", "name": "Author"}]
    )
    return service, p, j


def run(s, who, target, action, data=None, kind="HRMS.Policy", key=None):
    row = s.platform.rows.get(target)
    return s.execute(
        who,
        target,
        Command(
            action=action,
            entity_type=kind,
            data=data or {},
            expected_revision=row["data"].get("revision", 0) if row else 0,
            idempotency_key=key or str(uuid4()),
        ),
    )["entity_id"]


def draft(s, **extra):
    return run(
        s,
        actor("author", "hrms_hr_full"),
        "new",
        "create",
        {
            "title": "Policy",
            "body": "Public description",
            "audience": "public",
            "approver_id": "approver",
            **extra,
        },
    )


def publish(s, id):
    run(s, actor("author", "hrms_hr_full"), id, "submit")
    run(s, actor("approver", "hrms_hr_full"), id, "approve")
    run(s, actor("author", "hrms_hr_full"), id, "publish")


def test_publication_requires_independent_approval_and_safe_projection(system):
    s, _p, _j = system
    id = draft(s)
    assert s.feed() == []
    with pytest.raises(AppError):
        run(s, actor("author", "hrms_hr_full"), id, "publish")
    run(s, actor("author", "hrms_hr_full"), id, "submit")
    with pytest.raises(AppError):
        run(s, actor("author", "hrms_hr_full"), id, "approve")
    run(s, actor("approver", "hrms_hr_full"), id, "approve")
    assert s.feed() == []
    run(s, actor("author", "hrms_hr_full"), id, "publish")
    item = s.feed()[0]
    assert item["title"] == "Policy"
    assert (
        not {
            "author_id",
            "approver_id",
            "publication_id",
            "revision",
            "hrms_operation_key",
        }
        & item.keys()
    )
    with pytest.raises(AppError):
        run(s, actor("author", "hrms_hr_full"), id, "edit", {})
    run(s, actor("author", "hrms_hr_full"), id, "pause")
    assert s.feed() == []


def test_revision_keeps_previous_publication_until_published_and_withdrawal_does_not_resurrect(
    system,
):
    s, _p, _j = system
    old = draft(s)
    publish(s, old)
    new = run(s, actor("author", "hrms_hr_full"), old, "new_revision")
    assert s.feed()[0]["id"] == old
    publish(s, new)
    assert [r["id"] for r in s.feed()] == [new]
    run(s, actor("author", "hrms_hr_full"), new, "pause")
    assert s.feed() == []
    run(s, actor("author", "hrms_hr_full"), old, "pause")
    with pytest.raises(AppError):
        run(s, actor("author", "hrms_hr_full"), old, "resume")


def test_audience_dates_calendar_and_jobs_scope(system):
    s, p, _j = system
    id = draft(s, audience="employees")
    publish(s, id)
    assert not s.feed() and len(s.feed(employee=True)) == 1
    assert not s.actions(
        actor("recruiter", "hrms_recruiter"), p.rows[id] | {"kind": "HRMS.Policy"}
    )
    with pytest.raises(AppError):
        run(s, actor("recruiter", "hrms_recruiter"), "new", "create", {})
    with pytest.raises(AppError):
        draft(s, public_url="javascript:alert(1)")
    with pytest.raises(AppError):
        run(
            s,
            actor("author", "hrms_hr_full"),
            "new",
            "create",
            {
                "title": "Holidays",
                "body": "Annual",
                "audience": "public",
                "approver_id": "approver",
                "year": 2026,
                "holidays": "2027-01-01 | New year",
            },
            kind="HRMS.HolidayCalendar",
        )
    future = draft(s, publish_from="2199-01-01")
    publish(s, future)
    assert not s.feed()


def test_stale_revision_and_transition_retry(system):
    s, p, _j = system
    id = draft(s)
    cmd = Command(
        action="submit", expected_revision=0, idempotency_key="stable-operation-key"
    )
    p.fail_trigger = "submit"
    with pytest.raises(AppError):
        s.execute(actor("author", "hrms_hr_full"), id, cmd)
    s.execute(actor("author", "hrms_hr_full"), id, cmd)
    assert p.rows[id]["state"] == "pending_approval"
    assert s.execute(actor("author", "hrms_hr_full"), id, cmd) == {"entity_id": id}
    with pytest.raises(AppError):
        s.execute(
            actor("approver", "hrms_hr_full"),
            id,
            Command(
                action="approve",
                expected_revision=0,
                idempotency_key="stale-operation-key",
            ),
        )


def test_cockpit_override_preserves_other_capabilities():
    who = actor("admin", "superadmin")
    changed = replace(who, cockpit_policy={"superadmin": []})
    assert "cockpit:view" not in capabilities(changed)
    assert "platform:configure" in capabilities(changed)
