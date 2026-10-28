"""Account bridges selected by configured native form IDs, not state names.
Native definitions and Users remain authoritative. No platform database access.
"""

import logging
import os
import secrets

from .errors import AppError
from .platform import Actor

ONBOARDING_ROLE = "hrms_onboarding_employee"
APPROVAL_TAG = "hrms:account-approval"
COMPLETE_TAG = "hrms:grant-employee-access"


def reconcile(service):
    platform = service.platform
    approval = os.getenv("HRMS_EMPLOYEE_APPROVAL_FORM_ID")
    complete = os.getenv("HRMS_EMPLOYEE_COMPLETE_FORM_ID")
    if not approval or not complete:
        return
    workflows = platform.call(
        "GET", "/workflow-state-machines", params={"scope": "published"}
    )["published_items"]
    workflows = [
        w
        for w in workflows
        if w["entity_type"] == "HRMS.Employee"
        and any(
            any(r["method_id"] == approval for r in s.get("method_refs", []))
            for s in w["definition"]["states"]
        )
    ]
    for workflow in workflows:
        states = {s["name"]: s for s in workflow["definition"]["states"]}
        offset = 0
        while True:
            page = platform.call(
                "GET",
                "/workflow-enrollments",
                params={
                    "machine_name": workflow["machine_name"],
                    "entity_type_name": "HRMS.Employee",
                    "limit": 200,
                    "offset": offset,
                },
            )
            for row in page["items"]:
                if (
                    row["workflow_id"] != workflow["id"]
                    or row["organization_id"] != platform.org
                    or row.get("archived_at")
                ):
                    continue
                refs = {
                    r["method_id"]
                    for r in states[row["current_state"]].get("method_refs", [])
                }
                if os.getenv("HRMS_EMPLOYEE_PROFILE_FORM_ID"):
                    try:
                        reconcile_profile_assignee(platform, workflow, row)
                    except AppError:
                        logging.getLogger(__name__).exception(
                            "Employee profile assignment needs attention: %s", row["entity_id"]
                        )
                        continue
                tags = ([APPROVAL_TAG] if approval in refs else []) + (
                    [COMPLETE_TAG] if complete in refs else []
                )
                if tags:
                    try:
                        reconcile_employee(service, workflow, row, tags)
                    except AppError:
                        logging.getLogger(__name__).exception(
                            "Employee account bridge needs attention: %s",
                            row["entity_id"],
                        )
            if page.get("scan_truncated"):
                raise AppError(502, "Employee account synchronization was truncated")
            if not page["has_more"]:
                break
            if not page["items"]:
                raise AppError(502, "Incomplete employee enrollment page")
            offset += len(page["items"])


def reconcile_profile_assignee(platform, workflow, enrollment):
    """Use native assignment and notifications for the linked employee's step.

    Native Assign User supports fixed users/originator, not an entity user field.
    The integration resolves that relationship without changing the workflow.
    """
    from .employee_work import is_employee_profile_step, is_owner_signoff_step

    record = platform.record(enrollment["entity_id"])
    if record["organization_id"] != platform.org:
        raise AppError(403, "Employee organization mismatch")
    if is_owner_signoff_step(workflow, enrollment["current_state"]):
        owner_id = record.get("owner_id")
        if not owner_id:
            raise AppError(409, "Final sign-off requires the initiating HR record owner")
        if record.get("assignee_id") != owner_id:
            platform.call("PUT", f"/entity-records/{enrollment['entity_id']}/assignee",
                          json={"assignee_id": owner_id})
        return
    user_id = record["data"].get("platform_user_id")
    if not user_id:
        return
    profile = is_employee_profile_step(workflow, enrollment["current_state"])
    assigned = record.get("assignee_id")
    if profile and assigned != user_id:
        platform.call("PUT", f"/entity-records/{enrollment['entity_id']}/assignee",
                      json={"assignee_id": user_id})
    elif not profile and assigned == user_id:
        # Subsequent steps return to the configured role's queue.
        platform.call("PUT", f"/entity-records/{enrollment['entity_id']}/assignee",
                      json={"assignee_id": None})


def reconcile_employee(service, workflow, enrollment, tags):
    p = service.platform
    eid = enrollment["entity_id"]
    actor = Actor("hrms-account-bridge", p.org, "", frozenset(), frozenset())
    with service.journal.lock(p.org) as db:
        record = p.record(eid)
        if record["organization_id"] != p.org:
            raise AppError(403, "Employee organization mismatch")
        data = record["data"]
        if data.get('employment_status') in {'offboarded', 'inactive'}:
            return  # An unfinished onboarding must not recreate access after departure.
        op = service.journal.operation(
            db, actor, "employee-account:" + eid, {"entity_id": eid}
        )
        roles = {r["name"]: r for r in p.call("GET", "/roles")}
        if ONBOARDING_ROLE not in roles:
            raise AppError(409, "Configure the native Onboarding Employee role first")
        identity = next(
            (u for u in p.users() if u["id"] == data.get("platform_user_id")), None
        )
        if APPROVAL_TAG in tags:
            email = str(data.get("work_email") or "").strip().lower()
            if not email or email.rsplit("@", 1)[-1] != service.domain:
                raise AppError(
                    409, "A company work email is required before account approval"
                )
            if identity is None:
                existing = next(
                    (u for u in p.users() if u["email"].lower() == email), None
                )
                if existing and existing["id"] != op.progress.get("created_user_id"):
                    raise AppError(
                        409,
                        "This email already has an account; administrator reconciliation is required",
                    )
                if existing:
                    identity = existing
                else:
                    if op.progress.get("create_requested"):
                        raise AppError(
                            409,
                            "Account creation outcome requires administrator reconciliation",
                        )
                    op.checkpoint(create_requested=True)
                    response = p.request(
                        "POST",
                        "/auth/register",
                        json={
                            "email": email,
                            "full_name": f"{data.get('first_name', '')} {data.get('last_name', '')}",
                            "password": secrets.token_urlsafe(48),
                            "role": ONBOARDING_ROLE,
                        },
                    )
                    if (
                        response.get("organization_id") != p.org
                        or response.get("approval_type") != "pending_org_admin"
                    ):
                        raise AppError(
                            409,
                            "Native account registration did not return a pending tenant user",
                        )
                    op.checkpoint(created_user_id=response["user_id"])
                    identity = next(
                        u for u in p.users() if u["id"] == response["user_id"]
                    )
                p.call(
                    "PUT",
                    f"/roles/users/{identity['id']}/role",
                    json={"role_id": roles[ONBOARDING_ROLE]["id"]},
                )
                data = {**data, "platform_user_id": identity["id"]}
                p.call("PUT", f"/entity-records/{eid}", json={"data": data})
            if (
                identity["organization_id"] != p.org
                or identity["email"].lower() != email
            ):
                raise AppError(409, "Employee account link does not match")
            if identity["status"] != "active":
                return
            # Native approval can grant Viewer; replace it with the restricted onboarding role.
            existing_account = op.progress.get("existing_account_id") == identity['id']
            if not existing_account and not op.progress.get("restricted_role_set"):
                p.call(
                    "PUT",
                    f"/roles/users/{identity['id']}/role",
                    json={"role_id": roles[ONBOARDING_ROLE]["id"]},
                )
                op.checkpoint(restricted_role_set=True)
            if not existing_account and not op.progress.get("invitation_requested"):
                op.checkpoint(invitation_requested=True)
                p.request("POST", "/auth/forgot-password", json={"email": email})
                op.checkpoint(invitation_sent=True)
            if not existing_account and not op.progress.get("invitation_sent"):
                raise AppError(
                    409, "Invitation outcome needs reconciliation before proceeding"
                )
            outgoing = [
                t
                for t in workflow["definition"]["transitions"]
                if t.get("from", t.get("from_state")) == enrollment["current_state"]
            ]
            if len(outgoing) != 1:
                raise AppError(
                    409, "Account Approval needs one configured outgoing transition"
                )
            p.call(
                "POST",
                f"/entities/{eid}/transitions",
                json={
                    "entity_id": eid,
                    "workflow_id": workflow["id"],
                    "trigger": outgoing[0]["trigger"],
                    "idempotency_key": "account-approved:" + eid,
                    "inputs": {"account_approved": True},
                },
            )
        elif COMPLETE_TAG in tags and identity and identity["status"] == "active":
            if op.progress.get('existing_account_id') == identity['id']:
                return  # Explicitly linked existing users retain their native role memberships.
            intended = roles.get(data.get("hrms_role"))
            if not intended or intended["name"] in {
                ONBOARDING_ROLE,
                "hrms_application_service",
            }:
                raise AppError(409, "The intended native employee role needs review")
            if not op.progress.get("access_granted"):
                p.call(
                    "PUT",
                    f"/roles/users/{identity['id']}/role",
                    json={"role_id": intended["id"]},
                )
                op.checkpoint(access_granted=True)
                service.journal.audit(
                    db, actor, "employee.onboarding.access_granted", eid
                )
