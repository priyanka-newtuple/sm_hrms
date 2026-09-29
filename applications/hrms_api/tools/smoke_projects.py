"""Local real-platform test; leaves a named project and allocation for review."""

import json
import os
from pathlib import Path

import httpx


def main():
    assert os.environ.get("HRMS_LOCAL_SMOKE") == "true"
    assert os.environ["HRMS_ORGANIZATION_ID"] == "11111111-1111-1111-1111-111111111111"
    accounts = json.loads(Path("/demo/users.json").read_text())["accounts"]
    manifest_path = Path("/demo/projects-smoke.json")
    saved = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    app = httpx.Client(base_url="http://hrms-app:8000/v1/api", timeout=240)
    headers = {}
    users = {}
    for role in (
        "project-manager",
        "delivery-manager",
        "superadmin",
        "hr-full",
        "employee",
        "finance",
    ):
        account = next(a for a in accounts if a["email"] == f"demo.{role}@newtuple.com")
        response = app.post(
            "/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
        assert response.status_code == 200, f"Login: {role}"
        headers[role] = {"Authorization": "Bearer " + response.json()["access_token"]}
        users[role] = account

    def board(role):
        response = app.get("/hrms/projects", headers=headers[role])
        assert response.status_code == 200, response.text
        return response.json()

    def action(role, target, trigger, data=None, suffix=""):
        key = "projects-smoke-v1-" + trigger + suffix
        if key not in saved:
            rows = board(role) if target != "new" else {}
            row = next(
                (
                    r
                    for group in ("projects", "requests", "allocations")
                    for r in rows.get(group, [])
                    if r["id"] == target
                ),
                None,
            )
            saved[key] = {
                "action": trigger,
                "data": data or {},
                "expected_revision": row["data"].get("revision", 0) if row else 0,
                "idempotency_key": key,
            }
            manifest_path.write_text(json.dumps(saved, indent=2) + "\n")
        path = (
            "/hrms/projects/actions"
            if target == "new"
            else f"/hrms/projects/{target}/actions"
        )
        response = app.post(path, headers=headers[role], json=saved[key])
        assert response.status_code == 200, (
            f"{trigger}: {response.status_code} {response.text}"
        )
        repeated = app.post(path, headers=headers[role], json=saved[key])
        assert repeated.status_code == 200 and repeated.json() == response.json(), (
            "Retry changed result"
        )
        print("PASS " + trigger + suffix, flush=True)
        return response.json()["entity_id"]

    customer = action(
        "delivery-manager",
        "new",
        "create_customer",
        {"name": "Local project test customer"},
    )
    details = {
        "name": "Local Projects Review",
        "customer_id": customer,
        "pm_id": users["project-manager"]["user_id"],
        "dm_id": users["delivery-manager"]["user_id"],
        "approver_id": users["superadmin"]["user_id"],
        "start_date": "2043-01-01",
        "end_date": "2043-12-31",
        "budget_amount": 100000,
        "billing_rate": 1000,
        "planned_hours": 500,
    }
    change = action("delivery-manager", "new", "create_project", details)
    project = next(
        r for r in board("delivery-manager")["requests"] if r["id"] == change
    )["data"]["project_id"]
    action("delivery-manager", change, "submit")
    denied = app.post(
        f"/hrms/projects/{change}/actions",
        headers=headers["delivery-manager"],
        json={"action": "approve", "idempotency_key": "projects-smoke-self-denied"},
    )
    assert denied.status_code == 403, denied.text
    action("superadmin", change, "approve")
    hr = board("hr-full")
    assert (
        "budget_amount"
        not in next(r for r in hr["projects"] if r["id"] == project)["data"]
    )
    assert (
        "billing_rate"
        not in next(r for r in hr["requests"] if r["id"] == change)["data"]["proposed"]
    )
    finance = board("finance")
    assert (
        next(r for r in finance["projects"] if r["id"] == project)["data"][
            "budget_amount"
        ]
        == 100000
    )
    options = app.get(
        "/hrms/projects/options", headers=headers["project-manager"]
    ).json()
    employee_id = users["employee"]["employee_entity_id"]
    payload = {
        "employee_id": employee_id,
        "project_role_id": options["project_roles"][0]["id"],
        "start_date": "2043-02-01",
        "end_date": "2043-04-30",
        "percentage": 50,
        "billing_rate": 900,
    }
    allocation_change = action(
        "project-manager", project, "request_allocation", payload
    )
    action("project-manager", allocation_change, "submit", suffix="-allocation")
    action("delivery-manager", allocation_change, "approve", suffix="-allocation")
    own = board("employee")
    allocation = next(
        a for a in own["allocations"] if a["data"]["project_id"] == project
    )
    assert "billing_rate" not in allocation["data"]
    denied = app.post(
        "/hrms/projects/actions",
        headers=headers["employee"],
        json={
            "action": "create_project",
            "data": details,
            "idempotency_key": "projects-smoke-employee-denied",
        },
    )
    assert denied.status_code == 403, denied.text
    invalid = app.post(
        f"/hrms/projects/{project}/capacity",
        headers=headers["project-manager"],
        json={
            "action": "preview",
            "data": payload,
            "idempotency_key": "projects-smoke-overlap-denied",
        },
    )
    assert invalid.status_code == 422 and "overlapping" in invalid.text, invalid.text
    amendment = action(
        "project-manager",
        project,
        "propose_amendment",
        {**details, "description": "Verified versioned amendment"},
        suffix="-project",
    )
    action("project-manager", amendment, "submit", suffix="-amendment")
    action("project-manager", amendment, "withdraw", suffix="-amendment")
    action("project-manager", amendment, "submit", suffix="-resubmission")
    action("superadmin", amendment, "approve", suffix="-amendment")
    assert (
        next(p for p in board("project-manager")["projects"] if p["id"] == project)[
            "data"
        ]["description"]
        == "Verified versioned amendment"
    )
    action("project-manager", project, "start", suffix="-project")
    action("project-manager", allocation["id"], "start", suffix="-allocation")
    pending = app.get(
        "/hrms/projects/pending-actions", headers=headers["delivery-manager"]
    )
    assert pending.status_code == 200 and pending.json() == [], pending.text
    print(
        "PASS real native project and allocation approvals, replay, commercial filtering, self-approval denial, employee scope and overlap prevention",
        flush=True,
    )


if __name__ == "__main__":
    main()
