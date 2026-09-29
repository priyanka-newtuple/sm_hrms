from datetime import date, timedelta

import pytest

from hrms.tests.conftest import EMPLOYEE, HR_BASIC, HR_FULL, PM_A, login_as

RECRUITER = "rhea.kapoor@newtuple.com"


@pytest.mark.asyncio
async def test_policy_and_holiday_publish_flow(client, seeded):
    await login_as(client, HR_BASIC)
    policy = (await client.post("/api/v1/hr-cockpit/policies", json={"title": "Test policy", "category": "People", "summary": "A policy awaiting publication", "body": "Published content", "effective_date": str(date.today())})).json()
    assert (await client.get("/api/v1/public/content/policies")).json() == []
    await client.post(f"/api/v1/hr-cockpit/policies/{policy['id']}/submit")
    holiday_date = date.today() + timedelta(days=410)
    holiday = (await client.post("/api/v1/hr-cockpit/holidays", json={"holiday_date": str(holiday_date), "name": "Test holiday", "location": "All locations"})).json()
    await client.post(f"/api/v1/hr-cockpit/holidays/{holiday['id']}/submit")
    await login_as(client, HR_FULL)
    assert (await client.get("/api/v1/work/summary")).json()["approvals"] >= 2
    await client.post(f"/api/v1/hr-cockpit/policies/{policy['id']}/approve")
    await client.post(f"/api/v1/hr-cockpit/holidays/{holiday['id']}/approve")
    assert any(x["title"] == "Test policy" for x in (await client.get("/api/v1/public/content/policies")).json())
    assert any(x["name"] == "Test holiday" for x in (await client.get("/api/v1/public/content/holidays")).json())


@pytest.mark.asyncio
async def test_recruiter_requisition_approval_publish_and_referral(client, seeded):
    await login_as(client, RECRUITER)
    assert (await client.get("/api/v1/hr-cockpit/dashboard")).status_code == 200
    jd = (await client.post("/api/v1/hr-cockpit/job-descriptions", json={"title": "Platform Engineer", "department": "Engineering", "level": "Senior", "responsibilities": "Build reliable platforms", "requirements": "Python and cloud experience"})).json()
    opening = (await client.post("/api/v1/hr-cockpit/openings", json={"job_description_id": jd["id"], "requisition_code": "TEST-REC-001", "hiring_manager_id": str(seeded["employee_ids"]["pm1"]), "openings": 1, "location": "Bengaluru", "work_mode": "Hybrid", "application_deadline": str(date.today() + timedelta(days=30))})).json()
    await client.post(f"/api/v1/hr-cockpit/openings/{opening['id']}/submit")
    assert (await client.get("/api/v1/public/content/openings")).json() == []
    await login_as(client, PM_A)
    work = (await client.get("/api/v1/work?view=todo")).json()
    assert any(x["source"] == "hr_content" and x["id"] == opening["id"] for x in work["items"])
    assert (await client.post(f"/api/v1/hr-cockpit/openings/{opening['id']}/approve")).status_code == 200
    await login_as(client, RECRUITER)
    assert (await client.post(f"/api/v1/hr-cockpit/openings/{opening['id']}/publish")).status_code == 200
    assert any(x["id"] == opening["id"] for x in (await client.get("/api/v1/public/content/openings")).json())
    await login_as(client, EMPLOYEE)
    response = await client.post(f"/api/v1/public/content/openings/{opening['id']}/referrals", json={"candidate_name": "Candidate One", "candidate_email": "candidate@example.com"})
    assert response.status_code == 201
