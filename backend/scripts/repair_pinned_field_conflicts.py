"""Find and clear PINNED_METHOD_FIELD_CONFLICT across every workflow.

One command. It scans every organization, works out which workflows are
broken, repairs them, and verifies each one afterwards.

The problem
-----------
A field a pinned Method Block provides must be described in exactly one place,
the block. `migrate_forms_to_method_blocks.py` set that up by stripping those
keys out of each workflow's own `entity_schema` "so the merge sees one source
for each key", and `_prepare_publishable_definition` enforces it: it seeds the
merge from the workflow's own fields and refuses any pinned field the workflow
defines differently.

The funnel editor's Form-sync broke the rule. Opening a workflow and changing
anything structural rebuilt `entity_schema.fields` wholesale from the entity
type's Form, putting a second, disagreeing copy of every pinned key back. The
copy also goes stale on its own, since it is a snapshot from the last publish,
so editing the method afterwards is enough to make it disagree.

The editor no longer does that. This repairs the workflows already carrying
the bad copy, which the editor would otherwise only fix when a human opens
them one at a time.

What it does to a broken workflow
---------------------------------
Drops from `entity_schema.fields` every key its pinned blocks provide, then
republishes through the application's own publish path. The engine re-merges
each key from the method itself, so the published definition ends up with the
same fields, described once. No field is lost.

Safety
------
  - Reports by default. Writes only with --apply.
  - Writes a JSON backup of every definition it is about to change, before
    changing anything. --restore rolls the repair back: it puts each saved
    definition back, makes it active again, and retires the version the
    repair published on top of it.
  - Republishes rather than editing the stored row. The active definition is
    what the engine serves, so stripping fields out of it in place would
    remove them from a running workflow until someone republished. A failed
    publish leaves the previous version active and untouched.
  - Only touches a workflow whose conflict it has actually confirmed, read
    through the same public validate the editor's Validate button calls. A
    workflow that publishes fine today is left alone rather than gaining a
    version for nothing.
  - Verifies each workflow after repairing it, and reports any that did not
    come back clean.
  - Idempotent. A second run finds nothing.
  - Exits non-zero if anything failed, so CI or a deploy step can stop.

Usage
-----
    WORKER_MODE=1 python scripts/repair_pinned_field_conflicts.py
    WORKER_MODE=1 python scripts/repair_pinned_field_conflicts.py --apply
    WORKER_MODE=1 python scripts/repair_pinned_field_conflicts.py --apply --org <id>
    WORKER_MODE=1 python scripts/repair_pinned_field_conflicts.py --restore <backup.json>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, datetime

os.environ.setdefault("WORKER_MODE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFLICT_CODE = "pinned_method_field_conflict"

# Outcome of looking at one workflow.
HEALTHY = "healthy"            # publishes today, nothing to do
BROKEN = "broken"              # has the conflict, repairable
BLOCKED = "blocked"            # has the conflict AND another error that publish will refuse
UNRELATED = "unrelated"        # fails for a different reason entirely, not ours
UNREADABLE = "unreadable"      # could not be evaluated


@dataclass
class Workflow:
    org_id: str
    org_name: str
    machine_name: str
    version: int
    definition: dict
    state: str = HEALTHY
    pinned_keys: set[str] = dc_field(default_factory=set)
    duplicated: list[str] = dc_field(default_factory=list)
    conflicts: list[str] = dc_field(default_factory=list)
    other_errors: list[str] = dc_field(default_factory=list)
    result: str = ""


def _actor(org_id: str) -> dict[str, object]:
    # actor_type=system makes the workflow access scope unrestricted; the
    # services only read organization_id and user_id otherwise.
    return {"organization_id": org_id, "actor_type": "system", "user_id": None, "roles": []}


def _services():
    import main  # WORKER_MODE=1: builds the service graph, no app, no migrations
    from common.configuration import Configuration
    from database.manager import DatabaseServiceManager

    config = Configuration()
    dsm = DatabaseServiceManager(config)
    managed = main._setup_generic_modules(None, dsm, config)
    by_name = {type(s).__name__: s for s in managed}
    return by_name["WorkflowServiceManager"], dsm


def _schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "modular_backend")


def _load(dsm, org_filter: str | None) -> list[Workflow]:
    """Every active, unarchived workflow, with its organization's name."""
    from sqlalchemy import text

    sql = text(
        f'SELECT w.organization_id, COALESCE(o.name, w.organization_id) AS org_name, '
        f'       w.machine_name, w.version, w.definition_json '
        f'FROM "{_schema()}".workflow_state_machines w '
        f'LEFT JOIN "{_schema()}".organizations o ON o.id = w.organization_id '
        f"WHERE w.is_active = true AND w.archived_at IS NULL "
        f"{'AND w.organization_id = :org' if org_filter else ''} "
        f"ORDER BY org_name, w.machine_name"
    )
    out: list[Workflow] = []
    with dsm.postgres_db_service().get_db_session() as session:
        rows = session.execute(sql, {"org": org_filter} if org_filter else {}).fetchall()
    for org_id, org_name, machine_name, version, definition_json in rows:
        try:
            definition = (
                json.loads(definition_json)
                if isinstance(definition_json, str)
                else definition_json
            )
        except (TypeError, ValueError) as exc:
            out.append(Workflow(org_id, org_name, machine_name, version, {},
                                state=UNREADABLE, result=f"definition_json unparseable: {exc}"))
            continue
        out.append(Workflow(org_id, org_name, machine_name, version, definition))
    return out


def _pinned_field_keys(workflow_svc, wf: Workflow) -> tuple[set[str], list[str]]:
    """Field keys the workflow's pinned methods provide, at their pinned versions.

    Resolved through the engine's own pin resolution, so this sees exactly what
    publish will see rather than a method's current fields. A pin that cannot
    be resolved is reported, never swallowed: it is its own publish failure and
    hiding it would make this run under-report.
    """
    from workflow.models.interface import MethodRef

    keys: set[str] = set()
    problems: list[str] = []
    service = workflow_svc.method_library_db_model_service
    if service is None:
        return keys, ["method library service unavailable"]
    for state in wf.definition.get("states", []):
        for ref in state.get("method_refs", []) or []:
            method_id = ref.get("method_id")
            if not method_id:
                continue
            try:
                _identity, version = workflow_svc._resolve_method_pin(
                    wf.org_id,
                    MethodRef(method_id=method_id, version_id=ref.get("version_id")),
                )
                for mf in service.list_version_fields(
                    organization_id=wf.org_id, method_version_id=version.version_id
                ):
                    if mf.field_key:
                        keys.add(mf.field_key)
            except Exception as exc:
                problems.append(
                    f"state '{state.get('name')}' pin {method_id}: {str(exc)[:120]}"
                )
    return keys, problems


def _validate(workflow_svc, org_id: str, machine_name: str, definition: dict):
    """Errors from the same public validate the editor's Validate button calls."""
    from workflow.models.interface import StateMachineDefinition
    from workflow.models.request import StateMachineValidateRequest

    report = workflow_svc.validate_candidate_workflow_for_actor(
        _actor(org_id),
        StateMachineValidateRequest(
            machine_name=machine_name,
            definition=StateMachineDefinition.model_validate(definition),
        ),
    ).validation_report
    errors = [i for i in (report.issues or []) if i.severity != "warning"]
    conflicts = [i for i in errors if getattr(i.code, "value", i.code) == CONFLICT_CODE]
    others = [i for i in errors if getattr(i.code, "value", i.code) != CONFLICT_CODE]
    return conflicts, others


def _classify(workflow_svc, workflows: list[Workflow]) -> None:
    for wf in workflows:
        if wf.state == UNREADABLE:
            continue
        pinned, problems = _pinned_field_keys(workflow_svc, wf)
        if problems:
            wf.state = UNREADABLE
            wf.result = "unresolvable pin: " + "; ".join(problems)
            continue
        wf.pinned_keys = pinned
        own = wf.definition.get("entity_schema", {}).get("fields", []) or []
        wf.duplicated = [f.get("field") for f in own if f.get("field") in pinned]

        try:
            conflicts, others = _validate(
                workflow_svc, wf.org_id, wf.machine_name, wf.definition
            )
        except Exception as exc:
            wf.state = UNREADABLE
            wf.result = f"could not validate: {str(exc)[:200]}"
            continue

        wf.conflicts = [i.message for i in conflicts]
        wf.other_errors = [
            f"{getattr(i.code, 'value', i.code)}: {i.message[:80]}" for i in others
        ]
        if conflicts and others:
            # Publish validates everything, so the repair cannot land until the
            # unrelated error is fixed by a human. Saying so beats a bare FAILED.
            wf.state = BLOCKED
        elif conflicts:
            wf.state = BROKEN
        elif others:
            wf.state = UNRELATED
        else:
            wf.state = HEALTHY


def _backup(workflows: list[Workflow], path: str) -> str:
    payload = {
        "taken_at": datetime.now(UTC).isoformat(),
        "schema": _schema(),
        "workflows": [
            {
                "org_id": wf.org_id,
                "machine_name": wf.machine_name,
                "version": wf.version,
                "definition": wf.definition,
            }
            for wf in workflows
        ],
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=1)
    return path


def _repair(workflow_svc, workflows: list[Workflow]) -> None:
    from workflow.models.interface import StateMachineDefinition
    from workflow.models.request import WorkflowDraftSeedRequest, WorkflowPublishRequest

    for wf in workflows:
        candidate = json.loads(json.dumps(wf.definition))  # never mutate the backup's copy
        candidate["entity_schema"]["fields"] = [
            f for f in candidate["entity_schema"]["fields"]
            if f.get("field") not in wf.pinned_keys
        ]
        try:
            draft = workflow_svc.seed_workflow_draft_for_actor(
                _actor(wf.org_id), wf.machine_name, WorkflowDraftSeedRequest()
            )
            published = workflow_svc.publish_workflow_for_actor(
                _actor(wf.org_id),
                draft.id,
                WorkflowPublishRequest(
                    definition=StateMachineDefinition.model_validate(candidate)
                ),
            )
            wf.result = f"published v{published.state_machine.version}"
        except Exception as exc:
            # A failed publish leaves the previous version active, untouched.
            wf.result = f"FAILED (previous version still active): {str(exc)[:220]}"


def _verify(workflow_svc, dsm, repaired: list[Workflow]) -> list[Workflow]:
    """Re-read and re-validate each repaired workflow. Never trust the write."""
    fresh = {(w.org_id, w.machine_name): w for w in _load(dsm, None)}
    still_bad: list[Workflow] = []
    for wf in repaired:
        if wf.result.startswith("FAILED"):
            still_bad.append(wf)
            continue
        current = fresh.get((wf.org_id, wf.machine_name))
        if current is None:
            wf.result += " | VERIFY: workflow not found after publish"
            still_bad.append(wf)
            continue
        try:
            conflicts, _others = _validate(
                workflow_svc, current.org_id, current.machine_name, current.definition
            )
        except Exception as exc:
            wf.result += f" | VERIFY failed: {str(exc)[:120]}"
            still_bad.append(wf)
            continue
        if conflicts:
            wf.result += f" | VERIFY: still conflicting ({len(conflicts)})"
            still_bad.append(wf)
        else:
            wf.result += " | verified clean"
    return still_bad


def _restore(dsm, path: str) -> int:
    """Roll back a previous --apply.

    The repair publishes a NEW version, so putting the old definition back is
    not enough on its own: the newer version is the active one and would still
    be served. This writes the saved definition back into its own row, makes
    that row active again, and deactivates every later version of the same
    workflow, which is what actually reverses the repair.
    """
    from sqlalchemy import text

    with open(path) as handle:
        payload = json.load(handle)
    entries = payload.get("workflows", [])
    reverted = 0
    with dsm.postgres_db_service().get_db_session() as session:
        for entry in entries:
            params = {
                "d": json.dumps(entry["definition"]),
                "o": entry["org_id"],
                "m": entry["machine_name"],
                "v": entry["version"],
            }
            # Put the saved definition back on its own version row.
            session.execute(
                text(
                    f'UPDATE "{_schema()}".workflow_state_machines '
                    f"SET definition_json = :d, is_active = true "
                    f"WHERE organization_id = :o AND machine_name = :m AND version = :v"
                ),
                params,
            )
            # Retire anything the repair published on top of it.
            result = session.execute(
                text(
                    f'UPDATE "{_schema()}".workflow_state_machines '
                    f"SET is_active = false "
                    f"WHERE organization_id = :o AND machine_name = :m AND version > :v"
                ),
                params,
            )
            reverted += 1
            _ = result
        session.commit()
    print(f"Rolled back {reverted} workflow(s) from {path}:")
    print("  saved definition restored and made active again")
    print("  any version the repair published on top is now inactive")
    return 0


def _report(workflows: list[Workflow], applied: bool, backup_path: str | None) -> int:
    broken = [w for w in workflows if w.state == BROKEN]
    blocked = [w for w in workflows if w.state == BLOCKED]
    unrelated = [w for w in workflows if w.state == UNRELATED]
    unreadable = [w for w in workflows if w.state == UNREADABLE]
    healthy = [w for w in workflows if w.state == HEALTHY]
    pinned = [w for w in workflows if w.pinned_keys]

    print()
    print("=" * 96)
    print(f"  scanned {len(workflows)} active workflow(s); {len(pinned)} pin a Method Block")
    print("=" * 96)

    def _table(title: str, group: list[Workflow], show_fields: bool) -> None:
        if not group:
            return
        print(f"\n{title} ({len(group)})")
        print("-" * 96)
        current_org = None
        for wf in group:
            if wf.org_name != current_org:
                current_org = wf.org_name
                print(f"\n  {current_org}  [{wf.org_id}]")
            line = f"    {wf.machine_name:<30} v{wf.version}"
            if show_fields and wf.duplicated:
                line += f"  duplicated: {', '.join(wf.duplicated[:6])}"
                if len(wf.duplicated) > 6:
                    line += f" (+{len(wf.duplicated) - 6} more)"
            print(line)
            if wf.result:
                print(f"        -> {wf.result}")
            for message in wf.other_errors[:2]:
                print(f"        ! {message}")

    _table("BROKEN by this bug, repairable", broken, True)
    _table("BLOCKED: has this bug AND an unrelated error that publish refuses",
           blocked, True)
    _table("Failing for unrelated reasons, NOT touched", unrelated, False)
    _table("Could not be evaluated", unreadable, False)

    print()
    print("=" * 96)
    print(f"  healthy                        {len(healthy)}")
    print(f"  broken by this bug             {len(broken)}"
          f"{'  (repaired)' if applied else '  (would be repaired)'}")
    print(f"  blocked by an unrelated error  {len(blocked)}   fix that error, then re-run")
    print(f"  unrelated failures, untouched  {len(unrelated)}")
    print(f"  could not evaluate             {len(unreadable)}")
    print("=" * 96)

    failures = [w for w in broken if "FAILED" in w.result or "VERIFY" in w.result]
    if applied:
        if backup_path:
            print(f"\n  backup written to {backup_path}")
            print(f"  roll back with:  --restore {backup_path}")
        if failures:
            print(f"\n  {len(failures)} workflow(s) did not come back clean. Listed above.")
        else:
            print("\n  Every repaired workflow was re-validated and is clean.")
    elif broken:
        print("\n  Report only, nothing was changed. Re-run with --apply to repair.")
    elif not broken and not blocked:
        print("\n  Nothing to repair.")

    return 1 if (failures or unreadable) else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find and clear PINNED_METHOD_FIELD_CONFLICT across every workflow.",
    )
    parser.add_argument("--apply", action="store_true",
                        help="repair the broken workflows (default: report only)")
    parser.add_argument("--org", default=None,
                        help="limit to one organization id (default: every organization)")
    parser.add_argument("--backup-dir", default=".",
                        help="where to write the pre-change backup (default: cwd)")
    parser.add_argument("--restore", default=None, metavar="FILE",
                        help="put back the definitions saved in a previous run's backup")
    args = parser.parse_args()

    workflow_svc, dsm = _services()

    if args.restore:
        return _restore(dsm, args.restore)

    workflows = _load(dsm, args.org)
    _classify(workflow_svc, workflows)
    broken = [w for w in workflows if w.state == BROKEN]

    backup_path = None
    if args.apply and broken:
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(
            args.backup_dir, f"pinned_field_repair_backup_{stamp}.json"
        )
        _backup(broken, backup_path)
        print(f"Backed up {len(broken)} definition(s) to {backup_path} before changing anything.")
        _repair(workflow_svc, broken)
        _verify(workflow_svc, dsm, broken)

    return _report(workflows, args.apply, backup_path)


if __name__ == "__main__":
    raise SystemExit(main())
