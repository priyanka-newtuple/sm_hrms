"""HRMS project orchestration. Native records/workflows own business data and state."""

import hashlib
from datetime import UTC, date, datetime, timedelta

from .catalog import pack_by_type
from .form_config import form_configuration
from .performance import PerformanceService, check, parse
from .policy import capabilities, require
from .project_catalog import (
    ALLOCATION,
    ALLOCATION_CHANGE,
    CHANGE,
    CUSTOMER,
    PROJECT,
    TYPES,
)
from .project_contracts import (
    AllocationInput,
    Comment,
    CustomerInput,
    ProjectInput,
    Release,
)
from .service import name

COMMERCIAL = {"budget_amount", "billing_rate", "contract_value"}
LIVE = {"planned", "active"}
EDITABLE = {"draft", "changes_requested", "rejected"}


def capacity_segments(rows, proposed, exclude=None):
    """Inclusive date ranges; peak commitments are calculated per actual interval."""
    start, end = (
        date.fromisoformat(proposed["start_date"]),
        date.fromisoformat(proposed["end_date"]),
    )
    events = {start: 0.0, end + timedelta(days=1): 0.0}
    duplicate = False
    for row in rows:
        d = row["data"]
        if (
            row["entity_id"] == exclude
            or row["state"] not in LIVE
            or d["employee_id"] != proposed["employee_id"]
        ):
            continue
        lo, hi = (
            max(start, date.fromisoformat(d["start_date"])),
            min(end, date.fromisoformat(d["end_date"])),
        )
        if lo > hi:
            continue
        duplicate |= d["project_id"] == proposed["project_id"]
        events[lo] = events.get(lo, 0) + d["percentage"]
        events[hi + timedelta(days=1)] = (
            events.get(hi + timedelta(days=1), 0) - d["percentage"]
        )
    boundaries, total, result = sorted(events), 0.0, []
    for i, point in enumerate(boundaries[:-1]):
        total += events[point]
        result.append(
            {
                "start_date": point.isoformat(),
                "end_date": (boundaries[i + 1] - timedelta(days=1)).isoformat(),
                "committed": round(total, 3),
                "proposed": proposed["percentage"],
                "total": round(total + proposed["percentage"], 3),
            }
        )
    return {
        "segments": result,
        "over_capacity": any(s["total"] > 100 for s in result),
        "duplicate": duplicate,
    }


class ProjectsService:
    def __init__(self, hrms):
        self.hrms, self.platform, self.journal = hrms, hrms.platform, hrms.journal

    def snapshot(self):
        result = {}
        for kind in TYPES:
            pack = pack_by_type(kind)
            states = self.platform.states(pack.machine_name) if pack.states else {}
            result[kind] = [
                {**r, "kind": kind, "state": states.get(r["entity_id"], "not_enrolled")}
                for r in self.platform.records(
                    kind,
                    [
                        "identifier",
                        "hrms_operation_key",
                        *[f["field"] for f in pack.fields],
                    ],
                )
            ]
        return result

    @staticmethod
    def find(snap, kind, entity_id):
        row = next((r for r in snap[kind] if r["entity_id"] == entity_id), None)
        check(row is not None, "Project record was not found", 404)
        return row

    def people(self, actor=None):
        return PerformanceService(self.hrms).user_options(getattr(actor, 'project_policy', None))

    def manage(self, actor, project):
        caps = capabilities(actor)
        return "project:manage_all" in caps or (
            "project:manage_assigned" in caps
            and project["data"].get("pm_id") == actor.user_id
        )

    def commercial(self, actor, project):
        caps = capabilities(actor)
        return "project:commercial_all" in caps or (
            "project:commercial_assigned" in caps
            and project["data"].get("pm_id") == actor.user_id
        )

    def visible(self, actor, project, snap):
        caps, d = capabilities(actor), project["data"]
        approver = "project:approve" in caps
        if project["state"] == "draft":
            return (
                d.get("created_by") == actor.user_id
                or approver
                or d.get("pm_id") == actor.user_id
            )
        if "project:read_all" in caps or self.manage(actor, project) or approver:
            return True
        own = {
            r["entity_id"]
            for r in self.hrms.employees()
            if r["data"].get("platform_user_id") == actor.user_id
        }
        return any(
            a["data"]["project_id"] == project["entity_id"]
            and a["data"]["employee_id"] in own
            and a["state"] != "cancelled"
            for a in snap[ALLOCATION]
        )

    def allowed(self, actor, row, snap):
        if row["kind"] == PROJECT:
            if not self.manage(actor, row) or not self.visible(actor, row, snap):
                return []
            active_request = any(
                r["data"]["project_id"] == row["entity_id"]
                and r["state"] not in {"approved", "rejected"}
                for r in snap[CHANGE]
            )
            actions = (
                []
                if active_request
                else (
                    ["propose_amendment"]
                    if row["state"] in {"planned", "active", "on_hold"}
                    else []
                )
            )
            if row["state"] in LIVE and "allocation:request" in capabilities(actor):
                actions += ["request_allocation"]
            actions += {
                "planned": ["start", "complete"],
                "active": ["hold", "complete"],
                "on_hold": ["resume", "complete"],
                "completed": ["archive"],
            }.get(row["state"], [])
            return actions
        project = self.find(snap, PROJECT, row["data"]["project_id"])
        if row["kind"] == ALLOCATION:
            return (
                (
                    ["amend_allocation", "release_allocation"]
                    + (
                        ["start"]
                        if row["state"] == "planned" and project["state"] == "active"
                        else []
                    )
                    + ["complete"]
                )
                if self.manage(actor, project) and "allocation:request" in capabilities(actor) and row["state"] in LIVE
                else []
            )
        d, state = row["data"], row["state"]
        if not d.get("approver_id"):
            return []  # Legacy requests require explicit approver migration before new decisions.
        actions = []
        if self.manage(actor, project) and d["requested_by_id"] == actor.user_id and (row["kind"] == CHANGE or "allocation:request" in capabilities(actor)):
            actions += (
                ["edit_request", "submit"]
                if state == "draft"
                else ["revise"]
                if state in {"changes_requested", "rejected"}
                else ["withdraw"]
                if state == "pending"
                else []
            )
            if d.get("kind") == "release" and "edit_request" in actions:
                actions.remove("edit_request")
        approver_cap = (
            "project:approve" in capabilities(actor)
            if row["kind"] == CHANGE or d["approver_id"] != project["data"]["dm_id"]
            else "project:manage_all" in capabilities(actor)
        )
        if (
            state == "pending"
            and d["approver_id"] == actor.user_id
            and d["requested_by_id"] != actor.user_id
            and approver_cap
        ):
            actions += ["approve", "request_changes", "reject"]
        return actions

    def options(self, actor):
        require(actor, "project:view")
        people = (
            self.people(actor)
            if (
                "project:create" in capabilities(actor)
                or "project:manage_all" in capabilities(actor)
            )
            else []
        )
        snap = self.snapshot()
        can_create = "project:create" in capabilities(actor)
        return {
            "customers": [
                {"id": r["entity_id"], "name": r["data"]["name"]}
                for r in snap[CUSTOMER]
            ]
            if can_create
            else [],
            "project_roles": self.project_roles(actor),
            "employees": [
                {"id": r["entity_id"], "name": name(r)}
                for r in self.hrms.employees()
                if r["data"].get("employment_status") == "active"
            ]
            if can_create
            else [],
            "pms": [
                u
                for u in people
                if "project:manage_assigned" in u["capabilities"]
                or "project:manage_all" in u["capabilities"]
            ],
            "dms": [u for u in people if "project:manage_all" in u["capabilities"]],
            "approvers": [
                u
                for u in people
                if "project:approve" in u["capabilities"] and u["id"] != actor.user_id
            ],
            "can_create": can_create,
            "can_create_customer": "customer:create" in capabilities(actor),
        }

    def project_roles(self, actor):
        """Current tenant form/picklist is the sole source of selectable staffing roles."""
        form = form_configuration(self.platform, actor, ALLOCATION)
        field = next((f for f in form['fields'] if f['field'] == 'project_role_id'), None)
        check(field is not None and field.get('enum_values') is not None,
              'Configure the Project role picklist in the Allocation form in Settings', 409)
        labels = field.get('enum_labels', {})
        return [{'id': value, 'name': labels.get(value, value)} for value in field['enum_values']]

    def project_role(self, actor, value):
        role = next((r for r in self.project_roles(actor) if r['id'] == value), None)
        check(role is not None, 'Choose a project role from the current configured picklist', 422)
        return role

    def project_values(self, actor, data, snap):
        values = parse(ProjectInput, data)
        if "project:manage_all" not in capabilities(actor):
            check(
                values["pm_id"] == actor.user_id,
                "Project managers must assign themselves as PM",
                403,
            )
        people = self.people(actor)

        def person(key, cap):
            row = next(
                (
                    u
                    for u in people
                    if u["id"] == values[key] and cap.intersection(u["capabilities"])
                ),
                None,
            )
            check(
                row is not None,
                f"Select an active authorized {key.removesuffix('_id')}",
                422,
            )
            return row

        pm = person("pm_id", {"project:manage_all", "project:manage_assigned"})
        dm = person("dm_id", {"project:manage_all"})
        approver = person("approver_id", {"project:approve"})
        check(approver["id"] != actor.user_id, "Self approval is not allowed", 422)
        customer = self.find(snap, CUSTOMER, values["customer_id"])
        values.update(
            pm_name=pm["name"],
            dm_name=dm["name"],
            customer_name=customer["data"]["name"],
        )
        note, approver_id = values.pop("note"), values.pop("approver_id")
        check(
            self.commercial(actor, {"data": values}),
            "Commercial write permission is required",
            403,
        )
        return values, approver_id, approver["name"], note

    def allocation_values(self, actor, project, data, snap, exclude=None):
        check(
            project["state"] in LIVE,
            "Allocations require an approved planned or active project",
            422,
        )
        values = parse(AllocationInput, data)
        check(
            project["data"]["start_date"]
            <= values["start_date"]
            <= values["end_date"]
            <= project["data"]["end_date"],
            "Allocation dates must be within the project dates",
            422,
        )
        employees = self.hrms.employees()
        employee = next(
            (
                r
                for r in employees
                if r["entity_id"] == values["employee_id"]
                and r["data"].get("employment_status") == "active"
            ),
            None,
        )
        check(employee is not None, "Choose an active employee", 422)
        role = self.project_role(actor, values["project_role_id"])
        values.update(
            project_id=project["entity_id"],
            employee_name=name(employee),
            project_role_name=role["name"],
        )
        people = self.people(actor)
        approver_id = (
            project["data"]["dm_id"]
            if actor.user_id != project["data"]["dm_id"]
            else values["approver_id"]
        )
        approver = next(
            (
                u
                for u in people
                if u["id"] == approver_id
                and u["id"] != actor.user_id
                and (
                    "project:approve" in u["capabilities"]
                    if actor.user_id == project["data"]["dm_id"]
                    else "project:manage_all" in u["capabilities"]
                )
            ),
            None,
        )
        check(approver is not None, "Choose an independent authorized approver", 422)
        preview = capacity_segments(snap[ALLOCATION], values, exclude)
        check(
            not preview["duplicate"],
            "An overlapping allocation already exists for this employee and project",
            422,
        )
        check(
            not preview["over_capacity"] or values["note"],
            "Over 100% capacity requires an exception reason and approval",
            422,
        )
        note = values.pop("note")
        values.pop("approver_id")
        check(
            self.commercial(actor, project),
            "Commercial write permission is required",
            403,
        )
        return values, approver["id"], approver["name"], note, preview

    def preview(self, actor, project_id, data, allocation_id=None):
        snap = self.snapshot()
        project = self.find(snap, PROJECT, project_id)
        check(
            self.manage(actor, project),
            "Project management permission is required",
            403,
        )
        if allocation_id:
            existing = self.find(snap, ALLOCATION, allocation_id)
            check(
                existing["data"]["project_id"] == project_id,
                "Allocation does not belong to this project",
                404,
            )
        return self.allocation_values(actor, project, data, snap, allocation_id)[4]

    def dashboard(self, actor):
        require(actor, "project:view")
        snap = self.snapshot()
        projects = [p for p in snap[PROJECT] if self.visible(actor, p, snap)]
        ids = {p["entity_id"]: p for p in projects}
        own = {
            e["entity_id"]
            for e in self.hrms.employees()
            if e["data"].get("platform_user_id") == actor.user_id
        }

        def item(row, project):
            data = {k: v for k, v in row["data"].items() if k != "hrms_operation_key"}
            if not self.commercial(actor, project):
                data = {k: v for k, v in data.items() if k not in COMMERCIAL}
                if "proposed" in data:
                    data["proposed"] = {
                        k: v for k, v in data["proposed"].items() if k not in COMMERCIAL
                    }
            return {
                "id": row["entity_id"],
                "kind": row["kind"],
                "state": row["state"],
                "data": data,
                "project_name": project["data"]["name"],
                "owner_name": project["data"]["pm_name"],
                "actions": self.allowed(actor, row, snap),
            }

        allocations = [
            a
            for a in snap[ALLOCATION]
            if a["data"]["project_id"] in ids
            and (
                "project:read_all" in capabilities(actor)
                or self.manage(actor, ids[a["data"]["project_id"]])
                or a["data"]["employee_id"] in own
            )
        ]
        changes = [
            c
            for kind in (CHANGE, ALLOCATION_CHANGE)
            for c in snap[kind]
            if c["data"]["project_id"] in ids
            and (
                self.manage(actor, ids[c["data"]["project_id"]])
                or c["data"]["requested_by_id"] == actor.user_id
                or c["data"].get("approver_id") == actor.user_id
                or (
                    "project:read_all" in capabilities(actor)
                    and c["state"] == "approved"
                )
            )
        ]
        # Customer contact/contract values are not exposed through project lookups.
        return {
            "projects": [item(p, p) for p in projects],
            "allocations": [item(a, ids[a["data"]["project_id"]]) for a in allocations],
            "requests": [item(c, ids[c["data"]["project_id"]]) for c in changes],
            "can_create": "project:create" in capabilities(actor),
            "can_create_customer": "customer:create" in capabilities(actor),
        }

    def workflows(self, actor):
        if "project:view" not in capabilities(actor):
            return []
        if "project:view" not in capabilities(actor):
            return []
        board = self.dashboard(actor)
        return [
            {
                "entity_id": r["id"],
                "entity_type": r["kind"],
                "title": r["project_name"]
                + (
                    f" · {r['data'].get('employee_name', '')}"
                    if r["kind"] == ALLOCATION
                    else ""
                ),
                "identifier": r["data"].get("identifier", ""),
                "current_state": r["state"],
                "workflow_label": pack_by_type(r["kind"]).label,
                "owner_name": r["data"].get("approver_name")
                if r["state"] == "pending"
                else r["data"].get("pm_name")
                or r["data"].get("requested_by_name")
                or r["owner_name"],
                "next_action": ", ".join(a.replace("_", " ") for a in r["actions"])
                or (
                    "Applied"
                    if r["data"].get("applied") == "yes"
                    else "Waiting for assigned owner"
                ),
                "progress": (
                    "Applied"
                    if r["data"].get("applied") == "yes"
                    else "Pending application"
                )
                if r["state"] == "approved"
                else r["data"].get("end_date", ""),
                "due_date": None,
                "leave": None,
                "leave_view": None,
            }
            for r in [*board["projects"], *board["requests"], *board["allocations"]]
        ]

    def plan(self, actor, target, request, snap):
        action, data, ops = request.action, request.data, []

        def create(kind, values, alias):
            ops.append({"op": "create", "kind": kind, "data": values, "target": alias})

        def patch(row, values):
            ops.append(
                {
                    "op": "patch",
                    "target": row["entity_id"],
                    "data": {**values, "revision": row["data"].get("revision", 0) + 1},
                }
            )

        def transition(row, trigger):
            ops.append(
                {"op": "transition", "target": row["entity_id"], "trigger": trigger}
            )

        def proposal(
            kind,
            project_id,
            values,
            approver,
            approver_name,
            note,
            revision,
            allocation_id="",
            change_kind="initial",
        ):
            person = next((u for u in self.people(actor) if u["id"] == actor.user_id), None)
            check(
                person is not None, "An active organization membership is required", 403
            )
            create(
                kind,
                dict(
                    project_id=project_id,
                    proposed=values,
                    approver_id=approver,
                    approver_name=approver_name,
                    requested_by_id=actor.user_id,
                    requested_by_name=person["name"],
                    note=note,
                    kind=change_kind,
                    expected_revision=revision,
                    revision=1,
                    applied="no",
                    **(
                        {"allocation_id": allocation_id}
                        if kind == ALLOCATION_CHANGE
                        else {}
                    ),
                ),
                "created",
            )

        if target == "new":
            if action == "create_customer":
                require(actor, "customer:create")
                values = parse(CustomerInput, data)
                check(
                    not any(
                        c["data"]["name"].casefold() == values["name"].casefold()
                        for c in snap[CUSTOMER]
                    ),
                    "Customer already exists",
                    422,
                )
                create(CUSTOMER, {**values, "created_by": actor.user_id}, "created")
                return ops
            check(action == "create_project", "Unknown project action", 422)
            require(actor, "project:create")
            values, approver, approver_name, note = self.project_values(
                actor, data, snap
            )
            create(
                PROJECT,
                {**values, "created_by": actor.user_id, "revision": 0},
                "project",
            )
            proposal(CHANGE, "$project", values, approver, approver_name, note, 0)
            return ops
        row = next(
            (
                r
                for kind in (PROJECT, CHANGE, ALLOCATION, ALLOCATION_CHANGE)
                for r in snap[kind]
                if r["entity_id"] == target
            ),
            None,
        )
        check(row is not None, "Project workflow was not found", 404)
        check(
            action in self.allowed(actor, row, snap),
            "This action is not available to you at this stage",
            403,
        )
        check(
            row["data"].get("revision", 0) == request.expected_revision,
            "This record changed. Refresh before submitting.",
            409,
        )
        d = row["data"]
        project = (
            row if row["kind"] == PROJECT else self.find(snap, PROJECT, d["project_id"])
        )
        if action == "propose_amendment":
            values, approver, approver_name, note = self.project_values(
                actor, data, snap
            )
            proposal(
                CHANGE,
                target,
                values,
                approver,
                approver_name,
                note,
                d["revision"],
                change_kind="amendment",
            )
        elif action in {"request_allocation", "amend_allocation", "release_allocation"}:
            check(
                not any(
                    c["data"].get("allocation_id") == target
                    and c["state"] not in {"approved", "rejected"}
                    for c in snap[ALLOCATION_CHANGE]
                ),
                "This allocation already has an open request",
                422,
            )
            if action == "release_allocation":
                release = parse(Release, data)
                payload = {
                    k: d[k]
                    for k in (
                        "employee_id",
                        "project_role_id",
                        "start_date",
                        "end_date",
                        "percentage",
                        "billable",
                        "billing_rate",
                    )
                }
                # Release remains available on paused projects, and cannot overbook capacity.
                original_state = project["state"]
                project["state"] = "active"
                values, approver, approver_name, note, _ = self.allocation_values(
                    actor, project, {**payload, **release}, snap, target
                )
                project["state"] = original_state
            else:
                values, approver, approver_name, note, _ = self.allocation_values(
                    actor,
                    project,
                    data,
                    snap,
                    target if action == "amend_allocation" else None,
                )
            proposal(
                ALLOCATION_CHANGE,
                project["entity_id"],
                values,
                approver,
                approver_name,
                note,
                d["revision"] if row["kind"] == ALLOCATION else 0,
                target if row["kind"] == ALLOCATION else "",
                {
                    "request_allocation": "initial",
                    "amend_allocation": "amendment",
                    "release_allocation": "release",
                }[action],
            )
        elif row["kind"] in {PROJECT, ALLOCATION}:
            if row["kind"] == PROJECT and action == "complete":
                check(
                    not any(
                        a["data"]["project_id"] == target and a["state"] in LIVE
                        for a in snap[ALLOCATION]
                    ),
                    "Complete or release live allocations first",
                    422,
                )
                check(
                    not any(
                        c["data"]["project_id"] == target and c["state"] == "pending"
                        for c in snap[ALLOCATION_CHANGE]
                    ),
                    "Resolve pending allocation requests first",
                    422,
                )
            transition(row, action)
            patch(row, {})
        elif action == "edit_request":
            check(
                d["kind"] != "release",
                "Release requests retain their original reason; reject this request to replace it",
                422,
            )
            if row["kind"] == CHANGE:
                values, approver, approver_name, note = self.project_values(
                    actor, data, snap
                )
            else:
                values, approver, approver_name, note, _ = self.allocation_values(
                    actor, project, data, snap, d.get("allocation_id") or None
                )
            patch(
                row,
                {
                    "proposed": values,
                    "approver_id": approver,
                    "approver_name": approver_name,
                    "note": note,
                },
            )
        elif action in {"reject", "request_changes"}:
            comment = parse(Comment, data)["comment"]
            patch(
                row,
                {
                    "decision_comment": comment,
                    "decided_by": actor.user_id,
                    "decided_at": datetime.now(UTC).isoformat(),
                },
            )
            transition(row, action)
        elif action in {"withdraw", "revise"}:
            if action == "revise":
                other = [
                    r
                    for r in snap[row["kind"]]
                    if r["entity_id"] != target
                    and r["state"] not in {"approved", "rejected"}
                    and (
                        r["data"]["project_id"] == d["project_id"]
                        if row["kind"] == CHANGE
                        else r["data"].get("allocation_id") == d.get("allocation_id")
                        and d.get("allocation_id")
                    )
                ]
                check(not other, "Another change request is already open", 422)
            transition(row, action)
            patch(row, {})
        elif action in {"submit", "approve"}:
            approver = next(
                (u for u in self.people(actor) if u["id"] == d["approver_id"]), None
            )
            needed = (
                "project:approve"
                if row["kind"] == CHANGE or d["approver_id"] != project["data"]["dm_id"]
                else "project:manage_all"
            )
            check(
                approver
                and needed in approver["capabilities"]
                and d["approver_id"] != d["requested_by_id"],
                "Assigned approver is no longer eligible",
                422,
            )
            proposed = d["proposed"]
            if row["kind"] == CHANGE:
                check(
                    project["data"]["revision"] == d["expected_revision"],
                    "Project changed; create a fresh amendment",
                    422,
                )
                check(
                    project["state"] in {"draft", "planned", "active", "on_hold"},
                    "Project is no longer editable",
                    422,
                )
                for a in snap[ALLOCATION]:
                    if (
                        a["data"]["project_id"] == project["entity_id"]
                        and a["state"] in LIVE
                    ):
                        check(
                            proposed["start_date"]
                            <= a["data"]["start_date"]
                            <= a["data"]["end_date"]
                            <= proposed["end_date"],
                            "Project dates conflict with committed allocations",
                            422,
                        )
            else:
                allocation = (
                    self.find(snap, ALLOCATION, d["allocation_id"])
                    if d.get("allocation_id")
                    else None
                )
                if allocation:
                    check(
                        allocation["state"] in LIVE
                        and allocation["data"]["revision"] == d["expected_revision"],
                        "Allocation changed; create a fresh request",
                        422,
                    )
                if d["kind"] != "release":
                    self.project_role(actor, proposed["project_role_id"])
                    check(
                        project["state"] in LIVE,
                        "Project must be planned or active",
                        422,
                    )
                    check(
                        project["data"]["start_date"]
                        <= proposed["start_date"]
                        <= proposed["end_date"]
                        <= project["data"]["end_date"],
                        "Allocation dates fall outside project dates",
                        422,
                    )
                    check(
                        any(
                            e["entity_id"] == proposed["employee_id"]
                            and e["data"].get("employment_status") == "active"
                            for e in self.hrms.employees()
                        ),
                        "Employee is no longer active",
                        422,
                    )
                    preview = capacity_segments(
                        snap[ALLOCATION], proposed, d.get("allocation_id")
                    )
                    check(
                        not preview["duplicate"],
                        "An overlapping allocation now exists",
                        422,
                    )
                    check(
                        not preview["over_capacity"] or d.get("note"),
                        "Capacity now exceeds 100%; withdraw and provide an exception reason",
                        422,
                    )
            transition(row, action)
            if action == "approve":
                if row["kind"] == CHANGE:
                    patch(project, proposed)
                    if project["state"] == "draft":
                        transition(project, "approve")
                elif d["kind"] == "initial":
                    create(
                        ALLOCATION,
                        {**proposed, "revision": 1, "created_by": d["requested_by_id"]},
                        "allocation",
                    )
                elif d["kind"] == "release":
                    transition(allocation, "cancel")
                    patch(allocation, {})
                else:
                    patch(allocation, proposed)
                if row["kind"] == ALLOCATION_CHANGE and d["kind"] != "release":
                    # Complete the ready project-allocation onboarding step only when this
                    # approver is also entitled to complete it. Native writes precede this step.
                    for case in self.hrms.onboarding(actor):
                        if case["employee_entity_id"] == proposed["employee_id"]:
                            for step in case["steps"]:
                                if step["sequence"] == 8 and step["can_complete"]:
                                    transition(
                                        {"entity_id": step["task_id"]}, "complete"
                                    )
                patch(
                    row,
                    {
                        "applied": "yes",
                        "decided_by": actor.user_id,
                        "decided_at": datetime.now(UTC).isoformat(),
                    },
                )
            else:
                patch(row, {})
        return ops

    def pending(self, actor):
        with self.journal.lock(actor.organization_id) as db:
            rows = db.execute(
                "SELECT operation_key, progress FROM operations WHERE organization_id=%s AND actor_id=%s AND result IS NULL AND progress ? 'project_request' ORDER BY updated_at",
                (actor.organization_id, actor.user_id),
            ).fetchall()
            return [
                dict(
                    idempotency_key=key.removeprefix("projects:"),
                    **progress["project_request"],
                )
                for key, progress in rows
            ]

    def execute(self, actor, target, request):
        require(actor, "project:view")
        check(actor.organization_id == self.platform.org, "Organization mismatch", 403)
        key = "projects:" + request.idempotency_key
        with self.journal.lock(actor.organization_id) as db:
            operation = self.journal.operation(
                db, actor, key, dict(target=target, **request.model_dump(mode="json"))
            )
            if operation.result:
                return operation.result
            pending = db.execute(
                "SELECT operation_key FROM operations WHERE organization_id=%s AND operation_key<>%s AND result IS NULL AND progress ? 'project_plan' LIMIT 1",
                (actor.organization_id, key),
            ).fetchone()
            check(
                not pending,
                "A project operation needs recovery. Its author must retry the original request.",
                409,
            )
            if "project_plan" not in operation.progress:
                plan = self.plan(actor, target, request, self.snapshot())
                operation.checkpoint(
                    project_plan=plan,
                    project_capabilities=sorted(capabilities(actor)),
                    project_request={
                        "target": target,
                        "action": request.action,
                        "data": request.data,
                        "expected_revision": request.expected_revision,
                    },
                    step=0,
                    refs={},
                )
            check(
                set(operation.progress.get("project_capabilities", []))
                <= capabilities(actor),
                "Your permissions changed; an administrator must reconcile this operation",
                403,
            )
            refs = operation.progress["refs"]
            for index in range(
                operation.progress["step"], len(operation.progress["project_plan"])
            ):
                step = operation.progress["project_plan"][index]
                marker = hashlib.sha256(
                    f"{actor.organization_id}:{key}:{index}".encode()
                ).hexdigest()
                values = {
                    k: refs[v[1:]]
                    if isinstance(v, str) and v.startswith("$") and v[1:] in refs
                    else v
                    for k, v in step.get("data", {}).items()
                }
                if step["op"] == "create":
                    rows = self.platform.records(step["kind"], ["hrms_operation_key"])
                    matches = [
                        r for r in rows if r["data"].get("hrms_operation_key") == marker
                    ]
                    check(
                        len(matches) <= 1,
                        "Duplicate project records require reconciliation",
                    )
                    if matches:
                        entity_id = matches[0]["entity_id"]
                    else:
                        check(
                            operation.progress.get("creating") != index,
                            "Creation outcome is uncertain; reconcile before retrying",
                        )
                        operation.checkpoint(creating=index)
                        entity_id = self.platform.create_record(
                            step["kind"],
                            {**values, "hrms_operation_key": marker},
                            actor.user_id,
                        )["entity_id"]
                    if pack_by_type(step["kind"]).states:
                        self.platform.enroll(
                            entity_id, pack_by_type(step["kind"]).machine_name
                        )
                    refs[step["target"]] = entity_id
                elif step["op"] == "patch":
                    record = self.platform.record(step["target"])
                    self.platform.call(
                        "PUT",
                        f"/entity-records/{step['target']}",
                        json={"data": {**record["data"], **values}},
                    )
                else:
                    self.platform.call(
                        "POST",
                        f"/entities/{step['target']}/transitions",
                        json={
                            "entity_id": step["target"],
                            "trigger": step["trigger"],
                            "idempotency_key": marker,
                            "inputs": {
                                "hrms_actor_id": actor.user_id,
                                "hrms_operation_key": key,
                            },
                        },
                    )
                operation.checkpoint(step=index + 1, refs=refs, creating=None)
            result = {
                "entity_id": refs.get("created", target),
                "action": request.action,
            }
            self.journal.audit(
                db,
                actor,
                f"projects:{request.action}",
                result["entity_id"],
                operation_key=key,
            )
            operation.finish(result)
            return result
