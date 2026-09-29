from datetime import timedelta

import pytest

from hrms.tests.conftest import (
    DELIVERY_MANAGER,
    EMPLOYEE,
    HR_BASIC,
    HR_FULL,
    PM_A,
    PM_B,
    SUPER_ADMIN,
    login_as,
)

pytestmark = pytest.mark.asyncio


async def _open_cycle(client, seeded):
    start = seeded["today"] - timedelta(days=1)
    await login_as(client, HR_FULL)
    cycle = await client.post(
        "/api/v1/performance/cycles",
        json={
            "name": "FY Performance Review",
            "description": "Annual goals and appraisal",
            "start_date": str(start),
            "end_date": str(start + timedelta(days=365)),
            "goal_due_date": str(start + timedelta(days=30)),
            "self_review_due_date": str(start + timedelta(days=300)),
            "manager_review_due_date": str(start + timedelta(days=330)),
        },
    )
    assert cycle.status_code == 201, cycle.text
    cycle_id = cycle.json()["id"]
    edited = await client.put(
        f"/api/v1/performance/cycles/{cycle_id}",
        json={
            "name": "FY Performance Review",
            "description": "Annual goals, appraisal, and calibration",
            "start_date": str(start),
            "end_date": str(start + timedelta(days=365)),
            "goal_due_date": str(start + timedelta(days=30)),
            "self_review_due_date": str(start + timedelta(days=300)),
            "manager_review_due_date": str(start + timedelta(days=330)),
        },
    )
    assert edited.status_code == 200, edited.text
    assert (await client.post(f"/api/v1/performance/cycles/{cycle_id}/submit")).status_code == 200

    await login_as(client, SUPER_ADMIN)
    work = (await client.get("/api/v1/work", params={"view": "todo"})).json()
    assert any(item["action_type"] == "performance_cycle_approval" for item in work["items"])
    approved = await client.post(
        f"/api/v1/performance/cycles/{cycle_id}/decision",
        json={"decision": "approve"},
    )
    assert approved.status_code == 200, approved.text
    return cycle_id


async def test_complete_performance_review_workflow(client, seeded):
    cycle_id = await _open_cycle(client, seeded)

    await login_as(client, EMPLOYEE)
    dashboard = (await client.get("/api/v1/performance/dashboard")).json()
    review = next(row for row in dashboard["my_reviews"] if row["cycle"]["id"] == cycle_id)
    review_id = review["id"]
    for title, weight in (("Delivery outcomes", 60), ("Technical growth", 40)):
        goal = await client.post(
            f"/api/v1/performance/reviews/{review_id}/goals",
            json={
                "title": title,
                "description": "",
                "category": "delivery" if weight == 60 else "learning",
                "measurement": "Measurable completion criteria",
                "weight": weight,
                "target_date": str(seeded["today"] + timedelta(days=200)),
                "progress": 0,
                "evidence": "",
            },
        )
        assert goal.status_code == 201, goal.text
    assert (await client.post(f"/api/v1/performance/reviews/{review_id}/goals/submit")).status_code == 200

    await login_as(client, PM_A)
    forbidden = await client.post(f"/api/v1/performance/reviews/{review_id}/goals/decision", json={"decision": "approve"})
    assert forbidden.status_code == 403

    await login_as(client, PM_B)
    manager_work = (await client.get("/api/v1/work", params={"view": "todo"})).json()
    assert any(item["title"].startswith("Approve goals") for item in manager_work["items"])
    assert (
        await client.post(f"/api/v1/performance/reviews/{review_id}/goals/decision", json={"decision": "approve"})
    ).status_code == 200

    await login_as(client, EMPLOYEE)
    self_review = await client.post(
        f"/api/v1/performance/reviews/{review_id}/self-review",
        json={"summary": "Delivered the committed outcomes.", "rating": 4},
    )
    assert self_review.status_code == 200, self_review.text
    assert self_review.json()["pending_with"] == "Arjun Kulkarni"

    await login_as(client, PM_A)
    feedback = (await client.get("/api/v1/performance/dashboard")).json()["feedback_requests"]
    request = next(row for row in feedback if row["review_id"] == review_id)
    assert request["project_name"] == "PM-A Project"
    assert (
        await client.post(
            f"/api/v1/performance/feedback/{request['id']}",
            json={"rating": 4, "contribution": "Strong project delivery", "collaboration": "Worked well"},
        )
    ).status_code == 200

    await login_as(client, PM_B)
    manager_review = await client.post(
        f"/api/v1/performance/reviews/{review_id}/manager-review",
        json={"summary": "Consistent delivery and growth.", "rating": 4},
    )
    assert manager_review.status_code == 200, manager_review.text

    await login_as(client, EMPLOYEE)
    private = (await client.get(f"/api/v1/performance/reviews/{review_id}")).json()
    assert "manager_rating" not in private

    await login_as(client, DELIVERY_MANAGER)
    calibration_queue = (await client.get("/api/v1/performance/dashboard")).json()["team_reviews"]
    assert any(row["id"] == review_id and row["status"] == "manager_submitted" for row in calibration_queue)
    calibrated = await client.post(
        f"/api/v1/performance/reviews/{review_id}/calibrate",
        json={"rating": 4, "comment": "Calibrated with the delivery cohort."},
    )
    assert calibrated.status_code == 200, calibrated.text

    await login_as(client, HR_FULL)
    published = await client.post(f"/api/v1/performance/reviews/{review_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["final_rating"] == 4

    await login_as(client, EMPLOYEE)
    visible = (await client.get(f"/api/v1/performance/reviews/{review_id}")).json()
    assert visible["final_rating"] == 4
    acknowledged = await client.post(
        f"/api/v1/performance/reviews/{review_id}/acknowledge",
        json={"comment": "Acknowledged"},
    )
    assert acknowledged.status_code == 200


async def test_cycle_creation_is_restricted_to_hr_full_and_super_admin(client, seeded):
    start = seeded["today"]
    payload = {
        "name": "Restricted cycle",
        "start_date": str(start),
        "end_date": str(start + timedelta(days=100)),
        "goal_due_date": str(start + timedelta(days=10)),
        "self_review_due_date": str(start + timedelta(days=70)),
        "manager_review_due_date": str(start + timedelta(days=90)),
    }
    await login_as(client, HR_BASIC)
    assert (await client.post("/api/v1/performance/cycles", json=payload)).status_code == 403
