import pytest

from hrms.tests.conftest import EMPLOYEE, FINANCE, HR_BASIC, HR_FULL, SUPER_ADMIN, login_as

pytestmark = pytest.mark.asyncio


async def test_employee_cannot_view_customers(client, seeded):
    await login_as(client, EMPLOYEE)
    resp = await client.get("/api/v1/customers")
    assert resp.status_code == 403


async def test_finance_can_view_customers_with_contract_value(client, seeded):
    await login_as(client, FINANCE)
    resp = await client.get("/api/v1/customers")
    assert resp.status_code == 200


async def test_employee_can_view_own_profile(client, seeded):
    await login_as(client, EMPLOYEE)
    resp = await client.get(f"/api/v1/employees/{seeded['employee_ids']['eng_9']}")
    assert resp.status_code == 200
    assert resp.json()["salary_ctc"] is not None  # self always sees own compensation


async def test_hr_basic_sees_directory_but_not_salary(client, seeded):
    await login_as(client, HR_BASIC)
    resp = await client.get(f"/api/v1/employees/{seeded['employee_ids']['eng_9']}")
    assert resp.status_code == 200
    assert "salary_ctc" not in resp.json() or resp.json()["salary_ctc"] is None


async def test_hr_full_sees_salary(client, seeded):
    await login_as(client, HR_FULL)
    resp = await client.get(f"/api/v1/employees/{seeded['employee_ids']['eng_9']}")
    assert resp.status_code == 200
    assert resp.json()["salary_ctc"] is not None


async def test_employee_cannot_view_out_of_scope_colleague(client, seeded):
    await login_as(client, EMPLOYEE)
    resp = await client.get(f"/api/v1/employees/{seeded['employee_ids']['eng_10']}")
    assert resp.status_code == 404


async def test_unauthenticated_request_is_rejected(client, seeded):
    resp = await client.get("/api/v1/employees")
    assert resp.status_code == 401


async def test_employee_cannot_self_promote_role(client, seeded):
    await login_as(client, EMPLOYEE)
    roles = (await client.get("/api/v1/roles")).json()
    super_admin_id = next(r["id"] for r in roles if r["name"] == "Super Admin")
    employee_id = seeded["employee_ids"]["eng_9"]

    resp = await client.patch(
        f"/api/v1/employees/{employee_id}", json={"role_id": super_admin_id}
    )
    assert resp.status_code == 403

    # Safe self-service fields are still editable.
    resp = await client.patch(
        f"/api/v1/employees/{employee_id}", json={"phone": "+91-9000000000"}
    )
    assert resp.status_code == 200
    assert resp.json()["phone"] == "+91-9000000000"


async def test_hr_full_can_change_someone_elses_role(client, seeded):
    await login_as(client, HR_FULL)  # HR - Full, scope=ALL
    roles = (await client.get("/api/v1/roles")).json()
    employee_role_id = next(r["id"] for r in roles if r["name"] == "Employee")

    resp = await client.patch(
        f"/api/v1/employees/{seeded['employee_ids']['eng_9']}",
        json={"role_id": employee_role_id},
    )
    assert resp.status_code == 200


async def test_dev_login_disabled_in_production(client, seeded, monkeypatch):
    from hrms.auth import dev_login as dev_login_module

    monkeypatch.setattr(
        dev_login_module, "get_settings", lambda: type("S", (), {"is_production": True})()
    )
    resp = await client.post("/api/v1/auth/dev-login", json={"email": SUPER_ADMIN})
    assert resp.status_code == 401
