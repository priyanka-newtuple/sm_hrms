"""HR publishing orchestration using only public platform contracts."""

from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .catalog import pack_by_type
from .cockpit_catalog import INTERNAL, TYPES
from .errors import AppError
from .policy import capabilities, require, role_capabilities
from .workflow_config import configured_workflow_rows


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    entity_type: str = ""
    data: dict = Field(default_factory=dict)
    expected_revision: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


def check(ok, message, status=422):
    if not ok:
        raise AppError(status, message)


def can_author(actor, kind):
    caps = capabilities(actor)
    return "cockpit:author" in caps or ("cockpit:jobs" in caps and kind in TYPES[3:])


def public_fields(kind, data):
    # Explicit server allowlist, independent of form settings.
    keys = {
        "title",
        "body",
        "location",
        "public_url",
        "effective_date",
        "event_date",
        "end_date",
        "trainer",
        "year",
        "holidays",
        "department",
        "skills",
        "openings",
        "work_mode",
        "application_deadline",
    }
    return {k: v for k, v in data.items() if k in keys}


class CockpitService:
    def __init__(self, platform, journal):
        self.platform, self.journal = platform, journal

    def snapshot(self):
        result = []
        for kind in TYPES:
            pack = pack_by_type(kind)
            states = self.platform.states(pack.machine_name)
            for row in self.platform.records(
                kind, [f["field"] for f in pack.fields] + ["hrms_operation_key"]
            ):
                check(
                    row.get("organization_id", self.platform.org) == self.platform.org,
                    "Organization mismatch",
                    403,
                )
                result.append(
                    {
                        **row,
                        "kind": kind,
                        "state": states.get(row["entity_id"], "draft"),
                    }
                )
        return result

    def people(self, actor):
        result = []
        for u in self.platform.users():
            if u.get("status") != "active" or u.get("email") == self.platform.email:
                continue
            roles = self.platform.call("GET", f"/roles/users/{u['id']}/roles")
            caps = set().union(
                *(
                    role_capabilities(r["role_name"], None, actor.cockpit_policy)
                    for r in roles
                    if r["organization_id"] == actor.organization_id
                )
            )
            if "cockpit:approve" in caps and u["id"] != actor.user_id:
                result.append({"id": u["id"], "name": u["full_name"]})
        return result

    def actions(self, actor, row):
        d, s = row["data"], row["state"]
        caps = capabilities(actor)
        if "cockpit:view" not in caps:
            return []
        result = []
        if (
            can_author(actor, row["kind"])
            and d.get("author_id") == actor.user_id
            and s == "draft"
        ):
            result += ["edit", "submit"]
        if can_author(actor, row["kind"]) and d.get("published_at"):
            result += ["new_revision"]
        if (
            "cockpit:approve" in caps
            and d.get("approver_id") == actor.user_id
            and d.get("author_id") != actor.user_id
            and s == "pending_approval"
        ):
            result += ["approve", "request_changes"]
        if "cockpit:publish" in caps:
            result += {
                "approved": ["publish"],
                "published": ["pause", "close"],
                "paused": ["resume"],
                "closed": ["archive"],
            }.get(s, [])
        return result

    def board(self, actor):
        require(actor, "cockpit:view")
        rows = self.snapshot()
        presentations = configured_workflow_rows(
            self.platform,
            [{"entity_id": r["entity_id"], "next_action": ""} for r in rows],
        )
        by_id = {r["entity_id"]: r for r in presentations}
        result = []
        for r in rows:
            cfg = by_id[r["entity_id"]]
            triggers = {
                t["trigger"]
                for t in cfg["workflow_configuration"]["transitions"]
                if t["from_state"] == cfg["current_state"]
            }
            result.append(
                {
                    **r,
                    **cfg,
                    "actions": [
                        a
                        for a in self.actions(actor, r)
                        if a in {"edit", "new_revision"} or a in triggers
                    ],
                }
            )
        return {
            "items": result,
            "creatable": [t for t in TYPES if can_author(actor, t)],
            "approvers": self.people(actor),
            "people": [
                {"id": u["id"], "name": u["full_name"]}
                for u in self.platform.users()
                if u.get("status") == "active" and u.get("email") != self.platform.email
            ],
        }

    def feed(self, employee=False):
        latest = {}
        for row in self.snapshot():
            d = row["data"]
            if not d.get("published_at"):
                continue
            if d.get("publish_from") and d["publish_from"] > datetime.now(UTC).date().isoformat():
                continue
            key = d.get("publication_id") or row["entity_id"]
            if (
                key not in latest
                or d["published_at"] > latest[key]["data"]["published_at"]
            ):
                latest[key] = row
        today = datetime.now(UTC).date().isoformat()
        return [
            {
                "id": r["entity_id"],
                "entity_type": r["kind"],
                **public_fields(r["kind"], r["data"]),
            }
            for r in latest.values()
            if r["state"] == "published"
            and (employee or r["data"].get("audience") == "public")
            and (
                not r["data"].get("publish_from") or r["data"]["publish_from"] <= today
            )
            and (
                not r["data"].get("publish_until")
                or r["data"]["publish_until"] >= today
            )
            and (
                r["kind"] != TYPES[4]
                or not r["data"].get("application_deadline")
                or r["data"]["application_deadline"] >= today
            )
        ]

    def validate(self, actor, kind, data):
        check(kind in TYPES, "Unsupported content type")
        pack = pack_by_type(kind)
        fields = {f["field"]: f for f in pack.fields}
        forms = self.platform.call(
            "GET", "/forms/config", params={"entity_type": kind}
        )["items"]
        form = next(
            (
                f
                for f in forms
                if f["schema_key"] == pack.schema_key and f.get("is_active", True)
            ),
            None,
        )
        check(form is not None, "Content form is missing or inactive", 409)
        for f in form["fields"]:
            if f["field"] not in INTERNAL:
                fields[f["field"]] = {**fields.get(f["field"], {}), **f}
        allowed = set(fields) - INTERNAL | {"approver_id"}
        check(not set(data) - allowed, "Unrecognized or protected content fields")
        check(len(str(data)) < 100000, "Content is too large")
        for key, f in fields.items():
            if key in INTERNAL:
                continue
            if f.get("required"):
                check(data.get(key) not in (None, ""), f"{key} is required")
            value = data.get(key)
            if value in (None, ""):
                continue
            if f.get("enum_values"):
                check(value in f["enum_values"], f"{key} is not a configured option")
            if f["type"] in {"string", "text", "email", "enum", "date"}:
                check(isinstance(value, str), f"{key} must be text")
            if f["type"] == "date":
                try:
                    date.fromisoformat(value)
                except (ValueError, TypeError):
                    raise AppError(422, f"{key} must be an ISO date")
            if f["type"] == "integer":
                check(
                    isinstance(value, int) and not isinstance(value, bool),
                    f"{key} must be an integer",
                )
        check(
            data.get("audience") in {"public", "employees"}, "Select a valid audience"
        )
        check(
            not data.get("publish_from")
            or not data.get("publish_until")
            or data["publish_from"] <= data["publish_until"],
            "Publication dates are reversed",
        )
        if data.get("public_url"):
            url = urlsplit(data["public_url"])
            check(
                url.scheme == "https"
                and bool(url.hostname)
                and not url.username
                and not url.password,
                "Public links must use HTTPS without credentials",
            )
        if kind == TYPES[1]:
            check(
                not data.get("end_date") or data["event_date"] <= data["end_date"],
                "Event dates are reversed",
            )
        if kind == TYPES[2]:
            check(2000 <= data["year"] <= 2200, "Invalid calendar year")
            days = set()
            for line in data["holidays"].splitlines():
                try:
                    day, title = line.split("|", 1)
                    day = date.fromisoformat(day.strip())
                    check(
                        bool(title.strip())
                        and day.year == data["year"]
                        and day not in days,
                        "Invalid or duplicate holiday date/name",
                    )
                    days.add(day)
                except ValueError:
                    raise AppError(422, "Use YYYY-MM-DD | Holiday name on every line")
        people = {p["id"]: p["name"] for p in self.people(actor)}
        check(
            data.get("approver_id") in people,
            "Choose an active independent content approver",
        )
        if kind == TYPES[4]:
            check(data.get("openings", 0) > 0, "Openings must be positive")
            descriptions = {
                r["entity_id"]
                for r in self.snapshot()
                if r["kind"] == TYPES[3] and r["state"] == "published"
            }
            check(
                data.get("job_description_id") in descriptions,
                "Choose a published job description",
            )
        return {
            **{k: v for k, v in data.items() if v not in ("", None)},
            "approver_name": people[data["approver_id"]],
        }

    def execute(self, actor, target, cmd):
        require(actor, "cockpit:view")
        check(actor.organization_id == self.platform.org, "Organization mismatch", 403)
        key = "cockpit:" + cmd.idempotency_key
        with self.journal.lock(actor.organization_id) as db:
            op = self.journal.operation(
                db, actor, key, {"target": target, **cmd.model_dump()}
            )
            if op.result:
                return op.result
            pending = db.execute(
                "SELECT operation_key FROM operations WHERE organization_id=%s AND operation_key<>%s AND result IS NULL AND progress ? 'cockpit_plan' LIMIT 1",
                (actor.organization_id, key),
            ).fetchone()
            check(
                not pending,
                "A publishing operation needs recovery; retry its original request",
                409,
            )
            if "cockpit_plan" not in op.progress:
                rows = self.snapshot()
                row = next((r for r in rows if r["entity_id"] == target), None)
                kind = (
                    cmd.entity_type if target == "new" else row["kind"] if row else ""
                )
                check(kind in TYPES, "Content not found", 404)
                if target != "new":
                    check(
                        cmd.expected_revision == row["data"].get("revision", 0),
                        "Content changed; reload before continuing",
                        409,
                    )
                    check(
                        cmd.action in self.actions(actor, row),
                        "This action is not permitted",
                        403,
                    )
                else:
                    check(
                        cmd.action == "create" and can_author(actor, kind),
                        "Cannot create this content",
                        403,
                    )
                creating = cmd.action in {"create", "new_revision"}
                values = None
                if creating or cmd.action == "edit":
                    data = cmd.data
                    if cmd.action == "edit":
                        forms = self.platform.call(
                            "GET", "/forms/config", params={"entity_type": kind}
                        )["items"]
                        form = next(
                            (
                                f
                                for f in forms
                                if f["schema_key"] == pack_by_type(kind).schema_key
                            ),
                            {},
                        )
                        for field in form.get("fields", []):
                            if (
                                field.get("read_only")
                                and field["field"] not in INTERNAL
                            ):
                                check(
                                    data.get(field["field"])
                                    == row["data"].get(field["field"]),
                                    "A configured read-only field cannot be changed",
                                    403,
                                )
                    if cmd.action == "new_revision":
                        data = {
                            k: v
                            for k, v in row["data"].items()
                            if k not in INTERNAL or k == "approver_id"
                        }
                    data = self.validate(actor, kind, data)
                    if cmd.action == "new_revision":
                        check(
                            not any(
                                r["data"].get("publication_id")
                                == row["data"].get("publication_id")
                                and r["state"]
                                in {"draft", "pending_approval", "approved"}
                                for r in rows
                            ),
                            "A revision already awaits publication",
                            409,
                        )
                    values = {
                        **data,
                        "author_id": actor.user_id,
                        "author_name": next(
                            (
                                u["full_name"]
                                for u in self.platform.users()
                                if u["id"] == actor.user_id
                            ),
                            "HR",
                        ),
                        "publication_id": row["data"].get("publication_id", target)
                        if row
                        else str(uuid4()),
                        "revision": 0 if creating else cmd.expected_revision + 1,
                    }
                else:
                    if cmd.action == "resume":
                        check(
                            not any(
                                r["data"].get("publication_id")
                                == row["data"].get("publication_id")
                                and r["data"].get("published_at", "")
                                > row["data"].get("published_at", "")
                                for r in rows
                            ),
                            "A newer version has been published",
                            409,
                        )
                    if cmd.action == "submit":
                        self.validate(
                            actor,
                            kind,
                            {
                                k: v
                                for k, v in row["data"].items()
                                if k not in INTERNAL or k == "approver_id"
                            },
                        )
                    values = {**row["data"], "revision": cmd.expected_revision + 1}
                    if cmd.action in {"publish", "resume"}:
                        values["published_at"] = datetime.now(UTC).isoformat()
                steps = []
                if creating:
                    steps = [{"op": "create", "kind": kind, "data": values}]
                elif cmd.action == "edit":
                    steps = [{"op": "patch", "data": values}]
                else:
                    steps = [
                        {"op": "transition", "trigger": cmd.action},
                        {"op": "patch", "data": values},
                    ]
                op.checkpoint(
                    cockpit_plan=steps,
                    kind=kind,
                    target=target,
                    required_caps=sorted(capabilities(actor)),
                )
            check(
                set(op.progress["required_caps"]) <= capabilities(actor),
                "Permissions changed; operation requires reconciliation",
                403,
            )
            entity_id = op.progress.get("entity_id", target)
            for i, step in enumerate(op.progress["cockpit_plan"]):
                if i < op.progress.get("step", 0):
                    continue
                if step["op"] == "create":
                    matches = [
                        r
                        for r in self.snapshot()
                        if r["data"].get("hrms_operation_key") == key
                    ]
                    check(
                        len(matches) <= 1,
                        "Duplicate publication needs reconciliation",
                        409,
                    )
                    if matches:
                        entity_id = matches[0]["entity_id"]
                    else:
                        check(
                            not op.progress.get("creating"),
                            "Creation outcome uncertain; reconcile before retrying",
                            409,
                        )
                        op.checkpoint(creating=True)
                        entity_id = self.platform.create_record(
                            step["kind"],
                            {**step["data"], "hrms_operation_key": key},
                            actor.user_id,
                        )["entity_id"]
                    self.platform.enroll(
                        entity_id, pack_by_type(step["kind"]).machine_name
                    )
                elif step["op"] == "patch":
                    self.platform.call(
                        "PUT",
                        f"/entity-records/{entity_id}",
                        json={"data": step["data"]},
                    )
                else:
                    self.platform.call(
                        "POST",
                        f"/entities/{entity_id}/transitions",
                        json={
                            "entity_id": entity_id,
                            "trigger": step["trigger"],
                            "idempotency_key": key,
                            "inputs": {"hrms_actor_id": actor.user_id},
                        },
                    )
                op.checkpoint(step=i + 1, entity_id=entity_id)
            result = {"entity_id": entity_id}
            self.journal.audit(db, actor, "cockpit:" + cmd.action, entity_id, key)
            op.finish(result)
            return result

    def workflows(self, actor):
        if "cockpit:view" not in capabilities(actor):
            return []
        return [
            {
                "entity_id": r["entity_id"],
                "entity_type": r["kind"],
                "title": r["data"].get("title", "Untitled content"),
                "identifier": r["data"].get("identifier", ""),
                "current_state": r["state"],
                "workflow_label": pack_by_type(r["kind"]).label,
                "owner_name": r["data"].get("approver_name")
                if r["state"] == "pending_approval"
                else r["data"].get("author_name"),
                "next_action": ", ".join(r["actions"]),
                "progress": r["data"].get("audience", "employees"),
            }
            for r in self.board(actor)["items"]
        ]
