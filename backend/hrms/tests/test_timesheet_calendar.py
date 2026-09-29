from datetime import timedelta

import pytest

from hrms.tests.conftest import EMPLOYEE, HR_BASIC, HR_FULL, PM_A, PM_B, login_as

pytestmark = pytest.mark.asyncio


async def test_weekly_time_holidays_month_and_reporting_manager_approval(client, seeded):
    future = seeded["today"] + timedelta(days=700)
    week_start = future - timedelta(days=future.weekday())
    holiday_date = week_start + timedelta(days=1)

    await login_as(client, HR_BASIC)
    holiday = await client.post(
        "/api/v1/timesheets/holidays",
        json={"holiday_date": str(holiday_date), "name": "Foundation Day", "is_optional": False},
    )
    assert holiday.status_code == 201, holiday.text

    await login_as(client, EMPLOYEE)
    visible = await client.get("/api/v1/timesheets/holidays", params={"year": holiday_date.year})
    assert any(row["name"] == "Foundation Day" for row in visible.json())
    assert (
        await client.post(
            "/api/v1/timesheets/holidays",
            json={"holiday_date": str(holiday_date + timedelta(days=1)), "name": "Not allowed"},
        )
    ).status_code == 403

    week = await client.get("/api/v1/timesheets/week", params={"week_start": str(week_start)})
    assert week.status_code == 200, week.text
    assert str(seeded["project_a_id"]) in {row["id"] for row in week.json()["projects"]}
    blocked = await client.put(
        "/api/v1/timesheets/week",
        json={
            "week_start_date": str(week_start),
            "entries": [
                {
                    "project_id": str(seeded["project_a_id"]),
                    "work_date": str(holiday_date),
                    "hours": 8,
                    "task_details": "Holiday work",
                }
            ],
        },
    )
    assert blocked.status_code == 422

    work_date = week_start
    saved = await client.put(
        "/api/v1/timesheets/week",
        json={
            "week_start_date": str(week_start),
            "entries": [
                {
                    "project_id": str(seeded["project_a_id"]),
                    "work_date": str(work_date),
                    "hours": 7.5,
                    "task_details": "Implemented API validation",
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["entries"][0]["task_details"] == "Implemented API validation"
    submitted = await client.post("/api/v1/timesheets/week/submit", params={"week_start": str(week_start)})
    assert submitted.status_code == 200
    assert submitted.json()["entries"][0]["status"] == "submitted"
    assert submitted.json()["submission"]["pending_with_name"] == "Arjun Kulkarni"

    history = await client.get("/api/v1/timesheets/submissions")
    assert history.status_code == 200
    assert history.json()[0]["status"] == "submitted"
    assert history.json()[0]["pending_with_name"] == "Arjun Kulkarni"
    locked = await client.put(
        "/api/v1/timesheets/week",
        json={
            "week_start_date": str(week_start),
            "entries": [
                {
                    "project_id": str(seeded["project_a_id"]),
                    "work_date": str(week_start + timedelta(days=5)),
                    "hours": 2,
                    "task_details": "Late addition",
                }
            ],
        },
    )
    assert locked.status_code == 409

    await login_as(client, PM_A)
    assert not any(row["week_start_date"] == str(week_start) for row in (await client.get("/api/v1/timesheets/approvals")).json())
    await login_as(client, PM_B)
    queue = (await client.get("/api/v1/timesheets/approvals")).json()
    assert any(row["week_start_date"] == str(week_start) for row in queue)
    decision = await client.post(
        f"/api/v1/timesheets/approvals/{seeded['employee_ids']['eng_9']}/{week_start}/decision",
        json={"action": "approve", "comment": "Approved"},
    )
    assert decision.status_code == 200, decision.text

    await login_as(client, EMPLOYEE)
    approved_history = await client.get("/api/v1/timesheets/submissions")
    assert approved_history.json()[0]["status"] == "approved"
    assert approved_history.json()[0]["decided_by_name"] == "Arjun Kulkarni"
    month = await client.get("/api/v1/timesheets/month", params={"month": str(work_date.replace(day=1))})
    assert month.status_code == 200
    assert month.json()["total_hours"] == 7.5
    assert month.json()["entries"][0]["task_details"] == "Implemented API validation"


async def test_leave_application_manager_approval_and_time_block(client, seeded):
    future = seeded["today"] + timedelta(days=760)
    week_start = future - timedelta(days=future.weekday())
    leave_date = week_start + timedelta(days=2)
    await login_as(client, EMPLOYEE)
    leave = await client.post(
        "/api/v1/timesheets/leave-requests",
        json={"start_date": str(leave_date), "end_date": str(leave_date), "leave_type": "annual", "reason": "Personal"},
    )
    assert leave.status_code == 201, leave.text

    await login_as(client, PM_A)
    assert not any(
        row["id"] == leave.json()["id"]
        for row in (await client.get("/api/v1/timesheets/leave-requests", params={"approvals": True})).json()
    )
    await login_as(client, PM_B)
    pending = (await client.get("/api/v1/timesheets/leave-requests", params={"approvals": True})).json()
    assert any(row["id"] == leave.json()["id"] for row in pending)
    approved = await client.post(
        f"/api/v1/timesheets/leave-requests/{leave.json()['id']}/decision",
        json={"decision": "approve"},
    )
    assert approved.status_code == 200

    await login_as(client, EMPLOYEE)
    blocked = await client.put(
        "/api/v1/timesheets/week",
        json={
            "week_start_date": str(week_start),
            "entries": [
                {
                    "project_id": str(seeded["project_a_id"]),
                    "work_date": str(leave_date),
                    "hours": 8,
                    "task_details": "Should be blocked",
                }
            ],
        },
    )
    assert blocked.status_code == 422


async def test_hr_reporting_manager_can_approve_leave(client, seeded):
    leave_date = seeded["today"] + timedelta(days=820)
    await login_as(client, HR_BASIC)
    leave = await client.post(
        "/api/v1/timesheets/leave-requests",
        json={"start_date": str(leave_date), "end_date": str(leave_date), "leave_type": "casual"},
    )
    assert leave.status_code == 201, leave.text

    await login_as(client, HR_FULL)
    queue = (await client.get("/api/v1/timesheets/leave-requests", params={"approvals": True})).json()
    assert any(row["id"] == leave.json()["id"] for row in queue)
    decision = await client.post(
        f"/api/v1/timesheets/leave-requests/{leave.json()['id']}/decision",
        json={"decision": "approve"},
    )
    assert decision.status_code == 200, decision.text
