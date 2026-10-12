"""HR publishing orchestration using only public platform contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .catalog import pack_by_type
from .cockpit_catalog import INTERNAL, TYPES
from .errors import AppError
from .form_config import configured_form
from .policy import capabilities, require, role_capabilities
from .workflow_config import configured_workflow_rows

# Native field types a content value is checked against. `datetime` is where date
# fields land in the Field Library; the cockpit still stores ISO dates in them.
TEXT_TYPES = {"string", "text", "email", "enum", "date", "datetime", "phone", "url"}
INTEGER_TYPES = {"int", "integer"}
# Not yet public: seen only by the author, the approver and publishers.
UNPUBLISHED = {"draft", "pending_approval", "approved"}
# Holds a calendar's place for its year and location (drafts do not).
CLAIMING = {"pending_approval", "approved", "published", "paused"}
# Actions that are not workflow triggers, or use another trigger.
EDITS = {"edit", "new_revision", "change_approver"}
TRIGGERS = {"withdraw": "request_changes"}


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


def same_place(a, b):
    """Locations match ignoring case, and "Pune" matches "Pune, India"."""
    a, b = (a or "").strip().casefold(), (b or "").strip().casefold()
    return a == b or (bool(a) and bool(b) and (a in b or b in a))


def applicable_holidays(calendars, location):
    """Holiday dates for someone working at `location`: company-wide calendars (no location) and
    their location's. Without a known work location, or where calendars are not set up by
    location (none matches and none is company-wide), every published calendar applies, as before."""
    if location:
        calendars = [c for c in calendars if not c.get("location") or same_place(c["location"], location)] or calendars
    result = set()
    for calendar in calendars:
        for line in (calendar.get("holidays") or "").splitlines():
            if line.strip():
                result.add(line.split("|", 1)[0].strip())
    return result


def publication(row):
    return row["data"].get("publication_id") or row["entity_id"]


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

    def snapshot(self, kinds=TYPES):
        result = []
        for kind in kinds:
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
        """Active users, other than the actor, whose roles grant cockpit:approve."""
        candidates = [
            u
            for u in self.platform.users()
            if u.get("status") == "active"
            and u.get("email") != self.platform.email
            and u["id"] != actor.user_id
        ]
        # The platform only lists roles per user; fetch them concurrently instead of one by one.
        with ThreadPoolExecutor(max_workers=8) as pool:
            all_roles = list(
                pool.map(
                    lambda u: self.platform.call("GET", f"/roles/users/{u['id']}/roles"),
                    candidates,
                )
            )
        result = []
        for u, roles in zip(candidates, all_roles):
            caps = set().union(
                *(
                    role_capabilities(r["role_name"], None, actor.cockpit_policy)
                    for r in roles
                    if r["organization_id"] == actor.organization_id
                )
            )
            if "cockpit:approve" in caps:
                result.append({"id": u["id"], "name": u["full_name"]})
        return result

    @staticmethod
    def superseded(row, rows):
        """An earlier version of a publication whose later revision has been published."""
        d = row["data"]
        return bool(d.get("published_at")) and any(
            publication(r) == publication(row)
            and r["data"].get("published_at", "") > d["published_at"]
            for r in rows
        )

    def actions(self, actor, row, rows=()):
        d, s = row["data"], row["state"]
        caps = capabilities(actor)
        if "cockpit:view" not in caps or self.superseded(row, rows):
            return []  # The live version is the one to pause, close or revise.
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
        if s == "pending_approval":
            # The author can take it back; the author or a publisher can hand it to another
            # approver when the chosen one is away.
            if d.get("author_id") == actor.user_id:
                result += ["withdraw"]
            if d.get("author_id") == actor.user_id or "cockpit:publish" in caps:
                result += ["change_approver"]
        if "cockpit:publish" in caps:
            result += {
                "approved": ["publish"],
                "published": ["pause", "close"],
                "paused": ["resume"],
                "closed": ["archive"],
            }.get(s, [])
        return result

    @staticmethod
    def visible(actor, row):
        d = row["data"]
        return (
            row["state"] not in UNPUBLISHED
            or "cockpit:publish" in capabilities(actor)
            or actor.user_id in {d.get("author_id"), d.get("approver_id")}
        )

    @staticmethod
    def expired(row):
        d, today = row["data"], datetime.now(UTC).date().isoformat()
        return row["state"] == "published" and (
            (d.get("publish_until") and d["publish_until"] < today)
            or (row["kind"] == TYPES[4] and d.get("application_deadline") and d["application_deadline"][:10] < today)
        )

    def board(self, actor):
        require(actor, "cockpit:view")
        everything = self.snapshot()
        rows = [r for r in everything if self.visible(actor, r)]
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
                        for a in self.actions(actor, r, everything)
                        if a in EDITS or TRIGGERS.get(a, a) in triggers
                    ],
                    "superseded": self.superseded(r, everything),
                    "expired": bool(self.expired(r)),
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

    def feed(self, employee=False, kinds=TYPES):
        latest = {}
        for row in self.snapshot(kinds):
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

    def validate(self, actor, kind, data, current=None, submitting=False):
        """`current` is the record being edited, revised or submitted; None when creating. A draft
        may wait for its approver to be chosen; submitting needs one."""
        check(kind in TYPES, "Unsupported content type")
        pack = pack_by_type(kind)
        fields = {f["field"]: f for f in pack.fields}
        for f in configured_form(self.platform, kind)["fields"]:
            if f["field"] not in INTERNAL:
                core = fields.get(f["field"], {})
                # Settings may make a field required, but not relax one the content type depends on
                # (year, holidays, event date, openings...), which the checks below read directly.
                fields[f["field"]] = {**core, **f, "required": bool(core.get("required") or f.get("required"))}
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
            if f["type"] in TEXT_TYPES:
                check(isinstance(value, str), f"{key} must be text")
            if f["type"] == "date":
                try:
                    date.fromisoformat(value)
                except (ValueError, TypeError):
                    raise AppError(422, f"{key} must be an ISO date")
            if f["type"] == "datetime":
                try:
                    datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    raise AppError(422, f"{key} must be an ISO date")
            if f["type"] in INTEGER_TYPES:
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
        snapshot = self.snapshot()
        own = publication(current) if current else None
        if kind == TYPES[2]:
            check(2000 <= data["year"] <= 2200, "Invalid calendar year")
            # One live calendar per year and location; revise it rather than publish a second.
            check(
                not any(
                    r["kind"] == TYPES[2]
                    and publication(r) != own
                    and r["state"] in CLAIMING
                    and r["data"].get("year") == data["year"]
                    and (r["data"].get("location") or "").strip().casefold()
                    == (data.get("location") or "").strip().casefold()
                    for r in snapshot
                ),
                f"A {data['year']} holiday calendar for {data.get('location') or 'all locations'} already exists; revise that one instead",
                409,
            )
            days = set()
            for line in data["holidays"].splitlines():
                if not line.strip():
                    continue  # Blank lines between holidays are just spacing.
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
        if data.get("approver_id") or submitting:
            check(
                data.get("approver_id") in people,
                "Choose an active independent content approver",
            )
        if kind == TYPES[4]:
            check(data.get("openings", 0) > 0, "Openings must be positive")
            # An opening follows its job description across revisions: it points at the JD's
            # current published version, and is refused only once the JD is no longer published.
            chosen = next((r for r in snapshot if r["kind"] == TYPES[3] and r["entity_id"] == data.get("job_description_id")), None)
            versions = [
                r for r in snapshot
                if chosen and r["kind"] == TYPES[3] and publication(r) == publication(chosen)
                and (r["data"].get("published_at") or r["state"] in {"published", "paused"})
            ]
            latest = max(versions, key=lambda r: r["data"].get("published_at") or "") if versions else None
            check(latest and latest["state"] in {"published", "paused"},
                  "Choose a published job description; this one is no longer published")
            data = {**data, "job_description_id": latest["entity_id"]}
            active = {u["id"] for u in self.platform.users() if u.get("status") == "active"}
            check(data.get("hiring_manager_id") in active, "Choose an active hiring manager")
            check(
                not data.get("application_deadline")
                or data["application_deadline"][:10] >= datetime.now(UTC).date().isoformat(),
                "The application deadline has already passed",
            )
            # Revisions of one opening share its publication and keep its requisition code.
            check(
                not any(
                    r["kind"] == TYPES[4]
                    and r["data"].get("requisition_code") == data.get("requisition_code")
                    and r["entity_id"] != (current or {}).get("entity_id")
                    and not (own and publication(r) == own)
                    and r["state"] != "archived"
                    for r in snapshot
                ),
                "This requisition code is already used by another opening",
                409,
            )
        values = {k: v for k, v in data.items() if v not in ("", None)}
        if data.get("approver_id"):
            values["approver_name"] = people[data["approver_id"]]
        return values

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
            # An interrupted operation holds up only its own item (and, for creates, other creates,
            # so a retried create cannot duplicate a requisition code).
            pending = db.execute(
                "SELECT actor_id, progress FROM operations WHERE organization_id=%s AND operation_key<>%s AND result IS NULL AND progress ? 'cockpit_plan'",
                (actor.organization_id, key),
            ).fetchall()
            check(
                not any(
                    target in {progress.get("target"), progress.get("entity_id")}
                    for _, progress in pending
                ),
                "This item needs recovery: an interrupted publishing step must be retried with its original request",
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
                        cmd.action in self.actions(actor, row, rows),
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
                        for field in configured_form(self.platform, kind)["fields"]:
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
                        # The earlier approver may have left or be the reviser; the author then
                        # picks one before submitting.
                        if data.get("approver_id") not in {p["id"] for p in self.people(actor)}:
                            data.pop("approver_id", None)
                    data = self.validate(actor, kind, data, current=row)
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
                    checked = {}
                    if cmd.action == "submit":
                        checked = self.validate(
                            actor,
                            kind,
                            {
                                k: v
                                for k, v in row["data"].items()
                                if k not in INTERNAL or k == "approver_id"
                            },
                            current=row,
                            submitting=True,
                        )
                    values = {**row["data"], "revision": cmd.expected_revision + 1}
                    if checked.get("job_description_id"):
                        values["job_description_id"] = checked["job_description_id"]  # its JD's live version
                    if cmd.action == "change_approver":
                        approver = cmd.data.get("approver_id")
                        people = {p["id"]: p["name"] for p in self.people(actor)}
                        check(
                            approver in people
                            and approver not in {row["data"].get("author_id"), row["data"].get("approver_id")},
                            "Choose an active approver other than the author and the current approver",
                        )
                        values.update(approver_id=approver, approver_name=people[approver])
                    if cmd.action in {"publish", "resume"}:
                        values["published_at"] = datetime.now(UTC).isoformat()
                steps = []
                if creating:
                    steps = [{"op": "create", "kind": kind, "data": values}]
                elif cmd.action in {"edit", "change_approver"}:
                    steps = [{"op": "patch", "data": values}]
                else:
                    steps = [
                        {"op": "transition", "trigger": TRIGGERS.get(cmd.action, cmd.action)},
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
                    try:
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
                    except AppError as error:
                        if error.status < 500 and i == 0:
                            # The platform refused the first change, so nothing was applied: leave no recovery behind.
                            for field in ("cockpit_plan", "kind", "target", "required_caps", "step"):
                                op.progress.pop(field, None)
                            op.checkpoint()
                        raise
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
