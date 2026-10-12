from dataclasses import replace
from uuid import uuid4

import pytest
from hrms_app.cockpit import CockpitService, Command
from hrms_app.errors import AppError
from hrms_app.policy import capabilities
from test_performance import UNMIGRATED_TENANT, Journal, Platform, actor


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
        if method == "GET" and path in UNMIGRATED_TENANT:
            return UNMIGRATED_TENANT[path]
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
    with pytest.raises(AppError):  # the replaced version is no longer acted on; the live one is
        run(s, actor("author", "hrms_hr_full"), old, "pause")
    rows = s.snapshot()
    assert [s.superseded(r, rows) for r in rows if r["entity_id"] in {old, new}] == [True, False]


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


def test_migrated_content_types_are_validated(system):
    s, p, _ = system
    pinned = [{"name": "draft", "method_refs": [{"method_id": "block"}]}]
    schema = {
        "HRMS.Policy": [{"field": "publish_from", "type": "datetime"}],
        "HRMS.JobOpening": [{"field": "openings", "type": "int", "required": True}],
    }
    native = p.call

    def call(method, path, **kwargs):
        if method == "GET" and path == "/workflow-state-machines":
            return {"published_items": [
                {"entity_type": kind, "is_active": True, "name": kind,
                 "definition": {"states": pinned, "entity_schema": {"fields": fields}}}
                for kind, fields in schema.items()]}
        return native(method, path, **kwargs)

    p.call = call
    who = actor("hrms_super_admin")
    policy = {"title": "T", "body": "B", "audience": "employees", "approver_id": "approver"}
    assert s.validate(who, "HRMS.Policy", {**policy, "publish_from": "2026-10-12"})
    with pytest.raises(AppError, match="must be an ISO date"):
        s.validate(who, "HRMS.Policy", {**policy, "publish_from": "next week"})
    opening = {**policy, "job_description_id": "jd", "requisition_code": "R1", "hiring_manager_id": "approver"}
    with pytest.raises(AppError, match="openings must be an integer"):
        s.validate(who, "HRMS.JobOpening", {**opening, "openings": "2"})


HR = actor("author", "hrms_hr_full")
BASE = {"title": "T", "body": "B", "audience": "employees", "approver_id": "approver"}
CALENDAR = {**BASE, "year": 2027, "holidays": "2027-01-01 | New year\n\n2027-01-26 | Republic day\n   \n"}


def test_a_holiday_calendar_ignores_blank_lines(system):
    s, _, _ = system
    assert s.validate(HR, "HRMS.HolidayCalendar", CALENDAR)["holidays"] == CALENDAR["holidays"]


def test_settings_cannot_relax_fields_the_content_type_depends_on(system, monkeypatch):
    s, _, _ = system
    import hrms_app.cockpit as cockpit
    monkeypatch.setattr(cockpit, "configured_form", lambda platform, kind: {"fields": [
        {"field": "year", "type": "int", "required": False}, {"field": "holidays", "type": "text", "required": False}]})
    for missing in ("year", "holidays"):
        with pytest.raises(AppError) as error:
            s.validate(HR, "HRMS.HolidayCalendar", {k: v for k, v in CALENDAR.items() if k != missing})
        assert error.value.status == 422 and missing in error.value.detail


@pytest.fixture
def opening(system):
    s, p, _ = system
    jd = p.add("HRMS.JobDescription", {**BASE, "title": "Engineer"}, state="published")["entity_id"]
    live = p.add("HRMS.JobOpening", {**BASE, "job_description_id": jd, "requisition_code": "R-1",
                                     "hiring_manager_id": "approver", "openings": 1, "publication_id": "pub-1"},
                 state="published")
    return s, live, {**BASE, "job_description_id": jd, "requisition_code": "R-2", "hiring_manager_id": "approver", "openings": 2}


def test_a_valid_opening_passes(opening):
    s, _, data = opening
    assert s.validate(HR, "HRMS.JobOpening", data)["requisition_code"] == "R-2"


@pytest.mark.parametrize(("change", "status", "message"), [
    ({"hiring_manager_id": "ghost"}, 422, "active hiring manager"),
    ({"application_deadline": "2020-01-31"}, 422, "deadline has already passed"),
    ({"requisition_code": "R-1"}, 409, "already used"),
])
def test_openings_are_checked_on_the_server(opening, change, status, message):
    s, _, data = opening
    with pytest.raises(AppError) as error:
        s.validate(HR, "HRMS.JobOpening", {**data, **change})
    assert error.value.status == status and message in error.value.detail


def test_a_revision_keeps_its_openings_requisition_code(opening):
    s, live, data = opening
    assert s.validate(HR, "HRMS.JobOpening", {**data, "requisition_code": "R-1"}, current=live)


def submit(s, id, key):
    return s.execute(actor("author", "hrms_hr_full"), id,
                     Command(action="submit", expected_revision=0, idempotency_key=key))


def test_an_interrupted_step_only_holds_up_its_own_item(system):
    s, p, _j = system
    stuck, other = draft(s), draft(s, title="Other policy")
    p.fail_trigger = "submit"  # outcome unknown (503): kept for recovery
    with pytest.raises(AppError):
        submit(s, stuck, "stuck-submit")
    submit(s, other, "other-submit")
    assert p.rows[other]["state"] == "pending_approval"
    with pytest.raises(AppError, match="needs recovery"):
        submit(s, stuck, "second-try-with-new-key")


def test_a_refused_first_step_leaves_nothing_to_recover(system):
    s, p, j = system
    id = draft(s)
    p.fail_trigger, p.fail_status = "submit", 409
    with pytest.raises(AppError):
        submit(s, id, "refused-submit")
    assert not any("cockpit_plan" in op.progress for op in j.ops.values() if op.result is None)
    submit(s, id, "fresh-submit")
    assert p.rows[id]["state"] == "pending_approval"


def two_approvers(s):
    s.people = lambda who: [p for p in ({"id": "approver", "name": "Approver"}, {"id": "deputy", "name": "Deputy"},
                                        {"id": "author", "name": "Author"}) if p["id"] != who.user_id]


# HC-3: a pending item can be taken back or handed to another approver
def test_the_author_can_withdraw_a_pending_item(system):
    s, p, _j = system
    id = draft(s)
    run(s, actor("author", "hrms_hr_full"), id, "submit")
    run(s, actor("author", "hrms_hr_full"), id, "withdraw")
    assert p.rows[id]["state"] == "draft"


def test_a_pending_item_can_go_to_another_approver(system):
    s, p, _j = system
    two_approvers(s)
    id = draft(s)
    run(s, actor("author", "hrms_hr_full"), id, "submit")
    with pytest.raises(AppError):  # not the author
        run(s, actor("author", "hrms_hr_full"), id, "change_approver", {"approver_id": "author"})
    run(s, actor("author", "hrms_hr_full"), id, "change_approver", {"approver_id": "deputy"})
    assert p.rows[id]["data"]["approver_name"] == "Deputy"
    with pytest.raises(AppError):
        run(s, actor("approver", "hrms_hr_full"), id, "approve")
    run(s, actor("deputy", "hrms_hr_full"), id, "approve")


# HC-4: a revision does not inherit an approver who can no longer approve it
def test_a_revision_drops_an_approver_who_has_left_and_needs_one_to_submit(system):
    s, p, _j = system
    old = draft(s)
    publish(s, old)
    s.people = lambda who: [{"id": "deputy", "name": "Deputy"}]  # the original approver left
    new = run(s, actor("author", "hrms_hr_full"), old, "new_revision")
    assert "approver_id" not in p.rows[new]["data"]
    with pytest.raises(AppError, match="approver"):
        run(s, actor("author", "hrms_hr_full"), new, "submit")


# HC-5: drafts are seen by their author, their approver and publishers only
def test_unpublished_items_are_need_to_know(system):
    s, p, _j = system
    id = draft(s)
    row = s.snapshot()[0]
    assert s.visible(actor("author", "hrms_hr_basic"), row)
    assert s.visible(actor("approver", "hrms_hr_basic"), row)
    assert s.visible(actor("someone", "hrms_hr_full"), row)            # publishes content
    assert not s.visible(actor("colleague", "hrms_hr_basic"), row)
    assert not s.visible(actor("recruiter", "hrms_recruiter"), row)
    publish(s, id)
    assert s.visible(actor("recruiter", "hrms_recruiter"), s.snapshot()[0])


# HC-1: an opening follows its job description across revisions
def test_an_opening_keeps_working_after_its_job_description_is_revised(system, monkeypatch):
    s, p, _j = system
    p.users = lambda: [{"id": u, "full_name": u.title(), "status": "active"} for u in ("author", "approver", "manager")]
    jd = run(s, actor("author", "hrms_hr_full"), "new", "create", {"title": "Engineer", "body": "Build", "audience": "public",
             "approver_id": "approver"}, kind="HRMS.JobDescription")
    publish(s, jd)
    opening = run(s, actor("author", "hrms_hr_full"), "new", "create", {"title": "Engineer opening", "body": "Join",
                  "audience": "public", "approver_id": "approver", "job_description_id": jd, "openings": 1,
                  "hiring_manager_id": "manager", "requisition_code": "REQ-1"}, kind="HRMS.JobOpening")
    revised = run(s, actor("author", "hrms_hr_full"), jd, "new_revision")
    publish(s, revised)
    run(s, actor("author", "hrms_hr_full"), opening, "submit")
    assert p.rows[opening]["state"] == "pending_approval"
    assert p.rows[opening]["data"]["job_description_id"] == revised
    run(s, actor("author", "hrms_hr_full"), revised, "close")
    with pytest.raises(AppError, match="no longer published"):
        run(s, actor("author", "hrms_hr_full"), "new", "create", {"title": "Another", "body": "Join", "audience": "public",
            "approver_id": "approver", "job_description_id": jd, "openings": 1, "hiring_manager_id": "manager",
            "requisition_code": "REQ-2"}, kind="HRMS.JobOpening")


# HC-7: holidays follow the calendar's location
def test_holidays_apply_by_location():
    from hrms_app.cockpit import applicable_holidays
    calendars = [{"location": "", "holidays": "2026-01-26 | Republic Day"},
                 {"location": "Pune", "holidays": "2026-09-07 | Ganesh Chaturthi"},
                 {"location": "Bengaluru", "holidays": "2026-11-01 | Rajyotsava"}]
    assert applicable_holidays(calendars, "Pune, India") == {"2026-01-26", "2026-09-07"}
    assert applicable_holidays(calendars, None) == {"2026-01-26", "2026-09-07", "2026-11-01"}  # location unknown
    by_site = calendars[1:]
    assert applicable_holidays(by_site, "Remote") == {"2026-09-07", "2026-11-01"}  # not set up for them: all apply


def test_only_one_live_calendar_per_year_and_location(system):
    s, _p, _j = system
    calendar = {"title": "Holidays", "body": "Annual", "audience": "employees", "approver_id": "approver",
                "year": 2026, "location": "Pune", "holidays": "2026-09-07 | Ganesh Chaturthi"}
    first = run(s, actor("author", "hrms_hr_full"), "new", "create", calendar, kind="HRMS.HolidayCalendar")
    publish(s, first)
    run(s, actor("author", "hrms_hr_full"), "new", "create", {**calendar, "location": "Mumbai"}, kind="HRMS.HolidayCalendar")
    with pytest.raises(AppError, match="already exists"):
        run(s, actor("author", "hrms_hr_full"), "new", "create", {**calendar, "location": "pune "}, kind="HRMS.HolidayCalendar")
    revision = run(s, actor("author", "hrms_hr_full"), first, "new_revision")  # revising the same calendar is fine
    run(s, actor("author", "hrms_hr_full"), revision, "submit")
