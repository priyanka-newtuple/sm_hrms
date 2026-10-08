"""Migrate legacy Form fields onto the new flow: Field Library -> Method Blocks -> workflow states.

What the old flow is: every entity type's fields live inline in
`entity_type_schema.fields_json` ("Forms", edited under Settings -> Form Config).
What the new flow is: a field is defined once in the Field Library, bundled into
a Method Block, the block is tagged to the entity types it applies to and
attached to workflow states; on publish the engine merges the block's fields
into the published definition's `entity_schema.fields`, each stamped with the
states it came from. Records keep their values in `entities.data` under the
same keys either way.

This script builds the new-flow side for every active legacy Form, additively:

  1. Field Library: one field per (organization, field key), one version per
     distinct shape (type + type-level config). Same key with several shapes
     (e.g. `email` typed email on one form and string on another) becomes one
     field with sibling versions; whichever version is created last is the
     field's current one, in a fixed processing order (forms by created_at,
     then key; slots by position), so re-runs number them the same way.
  2. Method Blocks: one per active Form, named after the Form, holding the
     Form's fields in Form order with the Form's per-field label, placeholder
     and required flag; tagged to the Form's entity type.
  3. Workflows: every live workflow of that entity type gets the block(s)
     attached to EVERY state and is published as a new version through the
     application's own publish path. Pinning to every state is the
     behaviour-preserving default: a legacy Form shows all its fields in all
     states. Narrowing fields to states is a later, human decision.
     Fields the block now provides are removed from the workflow's own
     `entity_schema` first, so the merge sees one source for each key.

What it deliberately does NOT do:

  - Never writes `fields_json`, never deactivates or deletes a Form. Forms stay
    exactly as they are until the new flow is stable; deactivating a Form is
    the per-entity-type cutover switch, done later and by hand.
  - Migrates `__ref__:` slots (a Form's "Add from related entity" fields) into
    the Form's block as INHERITED fields: `ownership='inherited'` with the
    slot's decoded source (`source_entity_type`, `source_field_key`). The
    block field keeps the legacy TARGET key (e.g. `account_legal_name`, not
    `legal_name`), so records, filters, guards and templates keep reading the
    same key. On publish the engine pins the field into only the workflows
    that use the block, read-only, and resolves it from the linked record at
    read time. The existing mapping in `entity_type_relations.relation_metadata`
    is left exactly as it is: during the overlap both mechanisms produce the
    same key from the same parent record, and retiring a mapping is a later,
    per-entity-type, reversible decision made by hand.
    Reported per slot as REDUNDANT (a live mapping also exists) or RESTORED
    (no live mapping: it showed nothing before, most likely lost to the old
    replace-not-merge write, and resolves again through the block).
    Skipped, and reported, when the target key is dotted (never resolved at
    runtime), the source cannot be decoded, or no relation is declared from
    the source type to the Form's type: publish would refuse that pin and,
    with it, every other field in that workflow's publish.
  - Skips slots already carrying `library_field_id`, and the `identifier` key.
  - Skips a workflow whose version-0 draft differs from its active definition
    (someone's in-progress or stale edit) rather than overwriting that draft,
    unless --overwrite-drafts is given. Reported either way.
  - Entity types with no live workflow get their library fields and blocks
    created and tagged, and nothing attached: there is nothing to attach to.
  - A key that two Forms of the same entity type define differently (label,
    placeholder, required or shape) goes into the older Form's block only;
    the publish merge refuses two sources that disagree about one field.
    Identical definitions are kept in both, which the merge accepts.

Type corrections. Old workflows synced their `entity_schema` field types
through a lossy editor mapping (auto_number, json/table, multi_select,
currency, timer_duration all became `string`), and some drifted from the
Form afterwards. The block publishes each field with the Form's real type,
so the new version's schema can differ from the previous one. Every such
change is listed per workflow in the report. A guard or required_field that
was written against the wrong type fails the publish for that workflow (the
engine's own validation), which is reported for a human to fix.

Requires Python 3.12+, like the backend itself: the definition models use
`value in <Enum>` checks that raise TypeError on 3.11, which surfaces as
"has invalid persisted definition" for every workflow.

Dry run is the default and writes nothing: it prints the full plan and the
report. --apply performs it through the application services
(FieldLibraryServiceManager, MethodLibraryServiceManager,
WorkflowServiceManager.publish_workflow_for_actor), so every write goes
through the same validation the UI does. Re-running is safe: fields, versions
and blocks that already exist are recognised and reused, workflows whose
active version already carries the pins are left alone. A block created by an
earlier run that lacks inherited fields this plan now calls for is TOPPED UP:
the missing inherited fields are appended (a new block version; the block's
other fields are carried through untouched) and the workflows pinning it are
re-published against the new version. Plain fields a human removed from a
migrated block are never put back by default; they are listed as a note -
unless the block's Form is named on --sync-plain-fields, in which case a
plain field now missing from the block is topped up the same way an
inherited one is. Opt-in and named per Form on purpose: this is for "I just
added a field to this Form and want it back in the block," not a standing
policy, which would defeat the whole point of leaving a human's removal alone
by default.

Run from backend/ with the app's environment (DATABASE_URL, POSTGRES_APP_SCHEMA,
and whatever Configuration() requires):

    WORKER_MODE=1 python scripts/migrate_forms_to_method_blocks.py                # dry run
    WORKER_MODE=1 python scripts/migrate_forms_to_method_blocks.py --apply        # write
    WORKER_MODE=1 python scripts/migrate_forms_to_method_blocks.py --org <id>     # one org
    ... --report out.json                                                         # machine-readable report
    ... --sync-plain-fields <schema_key>[,<schema_key>...]                        # top up named Forms' missing plain fields too

WORKER_MODE=1 makes `main` build the service graph without starting the web
app or running migrations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from typing import Any

os.environ.setdefault("WORKER_MODE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa  # noqa: E402

# ─── constants ───────────────────────────────────────────────────────────────

# Type-level config that decides whether two usages are the same shape of a
# field. Lives on the Field Library version.
SHAPE_KEYS = (
    "enum_values",
    "picklist_id",
    "auto_number_config",
    "currency_config",
    "table_config",
    "document_config",
    "calc",
)
# Per-usage behaviour. Snapshotted onto the version from the first usage (the
# Fields screen reads required/placeholder off version.settings) and carried
# per block-field as label/placeholder/required.
USAGE_KEYS = (
    "required",
    "placeholder",
    "nullable",
    "default",
    "editable",
    "col_span",
    "ownership",
    "source",
)
REF_PREFIX = "__ref__:"
ENL_PREFIX = "__enl__:"
PLM_PREFIX = "__plm__:"
IDENTIFIER_KEY = "identifier"
BLOCK_MARKER = "[migrated-from-form:"  # + schema_key + "]" in the block description
# Catalogue config kinds whose published config the pin converter builds from
# the WHOLE settings dict rather than settings["<kind>_config"]
# (workflow/manager.py::_entity_field_from_method_field). Reported so the
# converter can be fixed before those fields are relied on.
CONVERTER_WHOLE_SETTINGS_KINDS = {"currency", "auto_number"}
# Engine types with no catalogue code of their own, migrated onto the nearest one.
ENGINE_TYPE_ALIASES = {"date": "datetime"}


def _schema() -> str:
    return os.environ.get("POSTGRES_APP_SCHEMA", "public")


def _defs() -> str:
    return f"{_schema()}_definitions"


def _runtime() -> str:
    return f"{_schema()}_runtime"


# ─── plan data ───────────────────────────────────────────────────────────────


@dataclass
class Slot:
    org_id: str
    schema_id: str
    schema_key: str
    form_name: str
    form_created_at: Any
    entity_type: str
    position: int
    entry: dict[str, Any]
    key: str
    engine_type: str
    code: str | None
    label: str
    encoding: str  # plain | enl | plm | ref
    extras: dict[str, Any]  # decoded enum_labels etc.; for ref: source_entity, source_field

    @property
    def inherited_source(self) -> tuple[str, str] | None:
        """(source entity type name, source field key) for a `__ref__` slot."""
        if self.encoding != "ref":
            return None
        return str(self.extras.get("source_entity") or ""), str(self.extras.get("source_field") or "")

    @property
    def shape_settings(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in SHAPE_KEYS:
            v = self.entry.get(k)
            if v in (None, [], {}, ""):
                continue
            out[k] = v
        return out

    @property
    def shape_key(self) -> str:
        return json.dumps({"code": self.code, "settings": self.shape_settings}, sort_keys=True)

    @property
    def usage(self) -> dict[str, Any]:
        return {k: self.entry[k] for k in USAGE_KEYS if k in self.entry}


@dataclass
class ShapePlan:
    shape_key: str
    code: str
    settings: dict[str, Any]  # what the version will store
    description: str
    slots: list[Slot]
    version_id: str | None = None  # existing or created
    action: str = "create"  # create | reuse


@dataclass
class FieldPlan:
    org_id: str
    key: str
    name: str
    shapes: list[ShapePlan]
    existing_field_id: str | None = None
    existing_type: str | None = None
    notes: list[str] = dc_field(default_factory=list)
    library_field_id: str | None = None


@dataclass
class BlockField:
    key: str
    shape_key: str
    label: str
    placeholder: str | None
    required: bool
    position: int
    # (source entity type name, source field key) when this block field is
    # inherited from a linked record; None for a field entered on the record.
    inherited_from: tuple[str, str] | None = None


@dataclass
class BlockPlan:
    org_id: str
    schema_id: str
    schema_key: str
    entity_type: str
    name: str
    description: str
    fields: list[BlockField]
    existing_method_id: str | None = None
    method_id: str | None = None
    version_id: str | None = None
    action: str = "create"  # create | reuse | top-up
    # Inherited fields the plan calls for that an existing (earlier-run) block
    # lacks; appended by the top-up. Keys, in block order.
    top_up_keys: list[str] = dc_field(default_factory=list)
    top_up_applied: bool = False
    # Plain fields the plan calls for that the existing block no longer has.
    # Reported, never re-added: a human may have removed them on purpose.
    missing_plain_keys: list[str] = dc_field(default_factory=list)


@dataclass
class WorkflowPlan:
    org_id: str
    machine_name: str
    active_row_id: str
    active_version: int
    entity_type: str
    states: list[str]
    blocks: list[str]  # schema_keys
    keys_to_drop: list[str]
    draft_status: str  # none | same | differs
    action: str  # publish | skip-draft-differs | skip-already-pinned
    retyped: list[str] = dc_field(default_factory=list)  # "key: old -> new" where the block corrects the type
    result: str = ""


@dataclass
class OrgPlan:
    org_id: str
    org_name: str
    fields: list[FieldPlan] = dc_field(default_factory=list)
    blocks: list[BlockPlan] = dc_field(default_factory=list)
    workflows: list[WorkflowPlan] = dc_field(default_factory=list)
    # __ref__ slots migrated into blocks as inherited fields, one line each,
    # tagged REDUNDANT (live mapping also exists) or RESTORED (no live mapping).
    ref_migrated: list[str] = dc_field(default_factory=list)
    ref_restored_count: int = 0
    # __ref__ slots that cannot be migrated, with the reason.
    ref_skipped: list[str] = dc_field(default_factory=list)
    skipped: list[str] = dc_field(default_factory=list)
    converter_caveats: list[str] = dc_field(default_factory=list)
    sibling_versions: list[str] = dc_field(default_factory=list)
    name_collisions: list[str] = dc_field(default_factory=list)
    deduplicated: list[str] = dc_field(default_factory=list)
    errors: list[str] = dc_field(default_factory=list)
    key_engine_type: dict[tuple[str, str], str] = dc_field(default_factory=dict)


# ─── decoding helpers ────────────────────────────────────────────────────────


def _humanise(key: str) -> str:
    return re.sub(r"[_\-.]+", " ", key).strip().title() or key


def _decode_description(entry: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """(label, encoding, extras) for one legacy slot."""
    raw = str(entry.get("description") or "").strip()
    key = str(entry.get("field") or "")
    if raw.startswith(REF_PREFIX):
        parts = raw.split(":")
        label = parts[3].strip() if len(parts) > 3 else ""
        return label or _humanise(key), "ref", {
            "source_entity": parts[1].strip() if len(parts) > 1 else "",
            "source_field": parts[2].strip() if len(parts) > 2 else "",
        }
    for prefix, enc in ((ENL_PREFIX, "enl"), (PLM_PREFIX, "plm")):
        if raw.startswith(prefix):
            try:
                meta = json.loads(raw[len(prefix):])
            except ValueError:
                meta = {}
            extras = {
                k: meta[k]
                for k in ("enum_labels", "enum_values_2", "enum_labels_2", "picklist_id_2")
                if k in meta and meta[k] not in (None, [], "")
            }
            return str(meta.get("label") or "").strip() or _humanise(key), enc, extras
    return raw or _humanise(key), "plain", {}


def _catalogue(conn) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """engine_type -> catalogue code (lowest sort_order wins), code -> config_kind, code -> engine_type."""
    rows = conn.execute(
        sa.text(
            f'SELECT code, engine_type, config_kind, sort_order FROM "{_defs()}".field_type_catalogue '
            f"WHERE engine_type IS NOT NULL ORDER BY sort_order"
        )
    ).all()
    by_engine: dict[str, str] = {}
    kinds: dict[str, str] = {}
    engine_of: dict[str, str] = {}
    for code, engine_type, config_kind, _ in rows:
        by_engine.setdefault(engine_type, code)
        kinds[code] = config_kind
        engine_of[code] = engine_type
    return by_engine, kinds, engine_of


def _resolve_code(entry: dict[str, Any], encoding: str, by_engine: dict[str, str]) -> tuple[str, str | None]:
    raw = str(entry.get("type") or "").strip().lower()
    if raw in {"number", "integer"}:
        raw = "int"
    # The catalogue has no plain-date type: a date lands on Date & Time, whose
    # value check accepts the same strings.
    raw = ENGINE_TYPE_ALIASES.get(raw, raw)
    if raw == "multi_select" and (entry.get("picklist_id") or encoding == "plm"):
        return raw, "picklist_multi"
    return raw, by_engine.get(raw)


# ─── planning (pure reads) ───────────────────────────────────────────────────


def _load_slots(conn, org_id: str, by_engine: dict[str, str], plan: OrgPlan) -> list[Slot]:
    rows = conn.execute(
        sa.text(
            f'SELECT id, schema_key, name, created_at, entity_type, fields_json '
            f'FROM "{_defs()}".entity_type_schema '
            f"WHERE organization_id = :org AND is_active = true "
            f"ORDER BY created_at, schema_key"
        ),
        {"org": org_id},
    ).all()
    slots: list[Slot] = []
    for schema_id, schema_key, form_name, created_at, entity_type, fields_json in rows:
        entries = fields_json if isinstance(fields_json, list) else json.loads(fields_json or "[]")
        for position, entry in enumerate(entries):
            if not isinstance(entry, dict):
                plan.skipped.append(f"form '{schema_key}' position {position}: entry is not an object")
                continue
            key = str(entry.get("field") or "").strip()
            if not key:
                plan.skipped.append(f"form '{schema_key}' position {position}: no field key")
                continue
            if entry.get("library_field_id"):
                plan.skipped.append(f"{entity_type}.{key} on '{schema_key}': already library-linked")
                continue
            if key == IDENTIFIER_KEY:
                plan.skipped.append(f"{entity_type}.{key} on '{schema_key}': identifier is never a library field")
                continue
            label, encoding, extras = _decode_description(entry)
            engine_type, code = _resolve_code(entry, encoding, by_engine)
            slot = Slot(
                org_id=org_id, schema_id=schema_id, schema_key=schema_key, form_name=form_name,
                form_created_at=created_at, entity_type=entity_type, position=position, entry=entry,
                key=key, engine_type=engine_type, code=code, label=label, encoding=encoding, extras=extras,
            )
            if encoding == "ref":
                # The legacy slot's type is display-only ('reference'), so it has
                # no catalogue code. The library field backing an inherited block
                # field is read-only on the record; text is the neutral shape.
                slot.code = slot.code or by_engine.get("string", "text")
                # The slot's label is the SOURCE field's ("Name"), which names the
                # shared library field badly and collides with the real "Name"
                # field. The library field carries the target key, so name it
                # after that ("Perkin Client Name"). On the record the engine
                # labels the value from its source anyway.
                slot.label = _humanise(key)
                slots.append(slot)  # migratability decided in _plan_refs
                continue
            if code is None:
                plan.skipped.append(
                    f"{entity_type}.{key} on '{schema_key}': engine type '{engine_type}' has no catalogue code"
                )
                continue
            slots.append(slot)
    return slots


def _plan_refs(conn, org_id: str, ref_slots: list[Slot], plan: OrgPlan) -> list[Slot]:
    """Decide which `__ref__` slots become inherited block fields; report the rest.

    A migratable slot needs a target key the engine can resolve (not dotted),
    a decodable source, and a live relation declared from the source type to
    the Form's entity type: `_check_owned_inheritance_pin` refuses a pin whose
    relation is missing, and one refused pin fails the whole workflow publish,
    taking every other field's migration down with it. Better to leave that one
    slot out and say so.
    """
    mapping_rows = conn.execute(
        sa.text(
            f"SELECT tet.name, m.value FROM \"{_defs()}\".entity_type_relations r "
            f'JOIN "{_defs()}".entity_types tet ON tet.entity_type_id = r.to_entity_type_id, '
            f"jsonb_each_text(r.relation_metadata) m "
            f"WHERE r.organization_id = :org AND r.deleted_at IS NULL "
            f"AND m.key LIKE '%.%' AND m.value LIKE '%.%'"
        ),
        {"org": org_id},
    ).all()
    live_targets = {(tgt_type, value.split(".", 1)[1]) for tgt_type, value in mapping_rows}
    declared = {
        (from_name, to_name)
        for from_name, to_name in conn.execute(
            sa.text(
                f'SELECT fet.name, tet.name FROM "{_defs()}".entity_type_relations r '
                f'JOIN "{_defs()}".entity_types fet ON fet.entity_type_id = r.from_entity_type_id '
                f'JOIN "{_defs()}".entity_types tet ON tet.entity_type_id = r.to_entity_type_id '
                f"WHERE r.organization_id = :org AND r.deleted_at IS NULL"
            ),
            {"org": org_id},
        ).all()
    }
    # The engine resolves entity types BY NAME at publish time
    # (_resolve_entity_type_id -> get_entity_type_record(name)). Two live types
    # sharing a name make that lookup a coin toss, and a pin resolved against
    # the wrong twin is refused as "no relation declared", failing the whole
    # workflow publish. Leave such slots out and say so.
    ambiguous = {
        name
        for (name,) in conn.execute(
            sa.text(
                f'SELECT name FROM "{_defs()}".entity_types '
                f"WHERE organization_id = :org AND archived_at IS NULL GROUP BY name HAVING count(*) > 1"
            ),
            {"org": org_id},
        ).all()
    }
    migratable: list[Slot] = []
    for s in sorted(ref_slots, key=lambda x: (x.form_created_at, x.schema_key, x.position)):
        source_entity, source_field = s.inherited_source or ("", "")
        line = f"{s.entity_type}.{s.key} on '{s.schema_key}' <- {source_entity}.{source_field}"
        if "." in s.key:
            plan.ref_skipped.append(f"{line}: dotted target key never resolves at runtime")
            continue
        if not source_entity or not source_field:
            plan.ref_skipped.append(f"{line}: source entity/field could not be decoded from the slot")
            continue
        twin = next((n for n in (source_entity, s.entity_type) if n in ambiguous), None)
        if twin is not None:
            plan.ref_skipped.append(
                f"{line}: entity type name '{twin}' is used by more than one live entity type in this "
                f"organization; the engine resolves types by name and would refuse the pin. Archive or "
                f"rename the duplicate, then re-run."
            )
            continue
        if (source_entity, s.entity_type) not in declared:
            plan.ref_skipped.append(
                f"{line}: no relation declared from '{source_entity}' to '{s.entity_type}'; "
                f"publish would refuse the pin. Declare the relation, then re-run."
            )
            continue
        if (s.entity_type, s.key) in live_targets:
            plan.ref_migrated.append(f"{line}  [REDUNDANT: live relation_metadata mapping also delivers it]")
        else:
            plan.ref_migrated.append(
                f"{line}  [RESTORED for records created from now on: no live relation_metadata rule, and a "
                f"record reads the workflow version it was enrolled in, so existing records stay blank until "
                f"the rule is also added under Relations -> Fields carried over]"
            )
            plan.ref_restored_count += 1
        migratable.append(s)
    return migratable


def _existing_fields(conn, org_id: str) -> dict[str, dict[str, Any]]:
    """lower(field_key) -> {id, type, name, versions: [(shape_key, version_id)]} for live fields."""
    rows = conn.execute(
        sa.text(
            f'SELECT f.library_field_id, f.field_key, f.field_type, f.name, '
            f"v.version_id, v.field_type, v.settings "
            f'FROM "{_defs()}".field_library_fields f '
            f'JOIN "{_defs()}".field_library_field_versions v ON v.library_field_id = f.library_field_id '
            f"WHERE f.organization_id = :org AND f.archived_at IS NULL ORDER BY v.version"
        ),
        {"org": org_id},
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for fid, key, ftype, name, vid, vtype, vsettings in rows:
        rec = out.setdefault(key.lower(), {"id": fid, "type": ftype, "name": name, "key": key, "versions": []})
        settings = vsettings if isinstance(vsettings, dict) else json.loads(vsettings or "{}")
        shape = json.dumps(
            {"code": vtype, "settings": {k: v for k, v in settings.items() if k in SHAPE_KEYS and v not in (None, [], {}, "")}},
            sort_keys=True,
        )
        rec["versions"].append((shape, vid))
    return out


def _plan_fields(slots: list[Slot], existing: dict[str, dict[str, Any]], kinds: dict[str, str], plan: OrgPlan) -> dict[str, FieldPlan]:
    by_key: dict[str, list[Slot]] = defaultdict(list)
    for s in slots:
        by_key[s.key.lower()].append(s)

    fields: dict[str, FieldPlan] = {}
    for lkey in sorted(by_key):
        group = by_key[lkey]
        group.sort(key=lambda s: (s.form_created_at, s.schema_key, s.position))
        shapes: dict[str, ShapePlan] = {}
        for s in group:
            sp = shapes.get(s.shape_key)
            if sp is None:
                settings = dict(s.shape_settings)
                if s.encoding != "ref":
                    # A ref slot's extras are its inheritance source; that lives
                    # on the block field, not on the shared library field.
                    settings.update(s.extras)
                settings.update(s.usage)  # snapshot of the first usage
                sp = ShapePlan(shape_key=s.shape_key, code=s.code or "", settings=settings, description=s.label, slots=[])
                shapes[s.shape_key] = sp
            sp.slots.append(s)
        ordered = list(shapes.values())
        first = group[0]
        fp = FieldPlan(org_id=first.org_id, key=first.key, name=first.label, shapes=ordered)

        ex = existing.get(lkey)
        if ex is not None:
            fp.existing_field_id = ex["id"]
            fp.existing_type = ex["type"]
            fp.library_field_id = ex["id"]
            fp.name = ex["name"]
            ex_by_shape = {shape: vid for shape, vid in ex["versions"]}
            for sp in fp.shapes:
                if sp.shape_key in ex_by_shape:
                    sp.version_id = ex_by_shape[sp.shape_key]
                    sp.action = "reuse"
            new = [sp for sp in fp.shapes if sp.action == "create"]
            if new:
                fp.notes.append(
                    f"library field '{fp.key}' already exists ({ex['type']}); "
                    f"{len(new)} new version(s) appended, the last one becomes current"
                )
        if len(fp.shapes) > 1:
            plan.sibling_versions.append(
                f"'{fp.key}' -> "
                + " | ".join(
                    f"{sp.code}: " + ", ".join(sorted({f'{x.entity_type}/{x.schema_key}' for x in sp.slots}))
                    for sp in fp.shapes
                )
                + f"  (current = {fp.shapes[-1].code})"
            )
        for sp in fp.shapes:
            if kinds.get(sp.code) in CONVERTER_WHOLE_SETTINGS_KINDS:
                plan.converter_caveats.append(
                    f"'{fp.key}' ({sp.code}): pin converter builds {sp.code}_config from the whole settings "
                    f"dict; check the published field after the converter fix"
                )
        fields[lkey] = fp

    # (name, type) uniqueness among live fields, case-insensitive: suffix the
    # later one with its entity type, then with its key.
    taken: dict[tuple[str, str], str] = {}
    for ex in existing.values():
        taken[(ex["name"].lower(), ex["type"])] = ex["key"].lower()
    for lkey in sorted(fields):
        fp = fields[lkey]
        if fp.existing_field_id:
            continue
        final_type = fp.shapes[-1].code
        candidates = [fp.name, f"{fp.name} ({fp.shapes[0].slots[0].entity_type})", f"{fp.name} ({fp.key})"]
        for cand in candidates:
            owner = taken.get((cand.lower(), final_type))
            if owner is None or owner == lkey:
                if cand != fp.name:
                    plan.name_collisions.append(f"'{fp.key}': name '{fp.name}' taken at type {final_type}; using '{cand}'")
                    fp.name = cand
                taken[(cand.lower(), final_type)] = lkey
                break
        else:
            plan.errors.append(f"'{fp.key}': could not find a free name")
    return fields


def _plan_blocks(
    conn, org_id: str, slots: list[Slot], plan: OrgPlan, sync_plain_fields: set[str] = frozenset()
) -> list[BlockPlan]:
    existing = {
        (desc or ""): mid
        for mid, desc in conn.execute(
            sa.text(
                f'SELECT method_id, description FROM "{_defs()}".method_library_methods '
                f"WHERE organization_id = :org AND archived_at IS NULL AND description LIKE :m"
            ),
            {"org": org_id, "m": f"%{BLOCK_MARKER}%"},
        ).all()
    }
    by_form: dict[str, list[Slot]] = defaultdict(list)
    meta: dict[str, Slot] = {}
    for s in slots:
        by_form[s.schema_key].append(s)
        meta.setdefault(s.schema_key, s)
    blocks: list[BlockPlan] = []
    # A key two Forms of the SAME entity type both define must reach the
    # publish merge from one block only, unless both define it identically
    # (label, placeholder, required and shape): the merge refuses any
    # disagreement. The first Form (oldest) keeps it; later Forms drop it.
    seen: dict[tuple[str, str], tuple[str, tuple]] = {}
    for schema_key in sorted(by_form, key=lambda k: (meta[k].form_created_at, k)):
        first = meta[schema_key]
        fields: list[BlockField] = []
        for s in sorted(by_form[schema_key], key=lambda s: s.position):
            bf = BlockField(
                key=s.key, shape_key=s.shape_key, label=s.label[:256],
                placeholder=(str(s.entry.get("placeholder"))[:256] if s.entry.get("placeholder") else None),
                required=bool(s.entry.get("required")), position=len(fields),
                inherited_from=s.inherited_source,
            )
            # An inherited and an entered definition of one key are two sources
            # that disagree, exactly like two labels would be.
            signature = (bf.label, bf.placeholder, bf.required, bf.shape_key, bf.inherited_from)
            owner = seen.get((s.entity_type, s.key.lower()))
            if owner is not None and owner[1] != signature:
                plan.deduplicated.append(
                    f"{s.entity_type}.{s.key}: defined differently on forms '{owner[0]}' and '{schema_key}'; "
                    f"kept in the block for '{owner[0]}' only"
                )
                continue
            seen.setdefault((s.entity_type, s.key.lower()), (schema_key, signature))
            fields.append(bf)
        description = f"Migrated from legacy form '{first.form_name}' {BLOCK_MARKER}{schema_key}]"
        bp = BlockPlan(
            org_id=org_id, schema_id=first.schema_id, schema_key=schema_key, entity_type=first.entity_type,
            name=(first.form_name or schema_key)[:256], description=description, fields=fields,
        )
        for desc, mid in existing.items():
            if f"{BLOCK_MARKER}{schema_key}]" in desc:
                bp.existing_method_id = mid
                bp.method_id = mid
                bp.action = "reuse"
                _plan_top_up(conn, bp, sync_plain_fields=sync_plain_fields)
        blocks.append(bp)
    return blocks


def _existing_block_fields(conn, method_id: str) -> tuple[str | None, dict[str, str | None]]:
    """(latest version id, {lower(field key): ownership}) of a block's current version."""
    rows = conn.execute(
        sa.text(
            f'SELECT mv.version_id, f.field_key, vf.ownership '
            f'FROM "{_defs()}".method_library_method_versions mv '
            f'LEFT JOIN "{_defs()}".method_library_method_version_fields vf ON vf.method_version_id = mv.version_id '
            f'LEFT JOIN "{_defs()}".field_library_fields f ON f.library_field_id = vf.library_field_id '
            f"WHERE mv.method_id = :mid AND mv.is_latest"
        ),
        {"mid": method_id},
    ).all()
    version_id = rows[0][0] if rows else None
    return version_id, {key.lower(): ownership for _, key, ownership in rows if key}


def _plan_top_up(conn, bp: BlockPlan, *, sync_plain_fields: set[str] = frozenset()) -> None:
    """Decide whether an earlier run's block needs fields appended.

    Inherited fields are always toppable: they are what this script did not
    migrate before. A plain field the block no longer has is reported, not
    restored, by default - a human may have removed it deliberately - UNLESS
    its schema_key was explicitly named on --sync-plain-fields, an operator
    saying "I just added this field to the Form and want it back in the
    block." Named or not, the mechanism is identical to an inherited top-up:
    one new block version, existing fields carried through unchanged, and
    every workflow still pinned to the old version gets repinned and
    republished by _apply_workflows - never a bare field_library_fields write
    with no one holding a fresh pin to it.
    """
    bp.version_id, present = _existing_block_fields(conn, bp.method_id)
    sync_this_block = bp.schema_key in sync_plain_fields
    for bf in bp.fields:
        if bf.key.lower() in present:
            continue
        if bf.inherited_from is not None or sync_this_block:
            bp.top_up_keys.append(bf.key)
        else:
            bp.missing_plain_keys.append(bf.key)
    if bp.top_up_keys:
        bp.action = "top-up"


def _plan_workflows(
    conn, org_id: str, blocks: list[BlockPlan], overwrite_drafts: bool, key_engine_type: dict[str, str]
) -> list[WorkflowPlan]:
    """`key_engine_type` maps (schema_key, lower(field key)) -> the engine type that form's block publishes it with."""
    blocks_by_type: dict[str, list[BlockPlan]] = defaultdict(list)
    for b in blocks:
        blocks_by_type[b.entity_type].append(b)
    if not blocks_by_type:
        return []
    rows = conn.execute(
        sa.text(
            f"SELECT id, machine_name, version, entity_type, definition_json "
            f'FROM "{_schema()}".workflow_state_machines '
            f"WHERE organization_id = :org AND is_active = true AND archived_at IS NULL "
            f"AND entity_type = ANY(:types) ORDER BY machine_name"
        ),
        {"org": org_id, "types": list(blocks_by_type)},
    ).all()
    drafts = {
        m: (json.loads(d) if isinstance(d, str) else d)
        for m, d in conn.execute(
            sa.text(
                f'SELECT machine_name, definition_json FROM "{_schema()}".workflow_state_machines '
                f"WHERE organization_id = :org AND version = 0"
            ),
            {"org": org_id},
        ).all()
    }
    plans: list[WorkflowPlan] = []
    for row_id, machine_name, version, entity_type, definition_json in rows:
        definition = json.loads(definition_json) if isinstance(definition_json, str) else definition_json
        states = [s.get("name") for s in definition.get("states", []) if s.get("name")]
        type_blocks = blocks_by_type[entity_type]
        # A block's `fields` is the FULL plan built from the Form - for a
        # reused block it can include plain fields the block does not
        # actually carry (`missing_plain_keys`: present on the Form, absent
        # from an earlier run's block, never silently re-added - see
        # `_plan_top_up`). Excluding them here is what `keys` promises to
        # its only two callers below: "the block will really supply this
        # key." Getting this wrong drops the field from the workflow's own
        # schema on the belief the block covers it, when nothing does.
        keys = {
            f.key for b in type_blocks for f in b.fields if f.key not in b.missing_plain_keys
        }
        # Only the workflow's OWN fields are droppable. A field the merge put
        # there from a block carries a non-empty `source_states`; leaving it
        # alone is what lets a second run recognise an already-migrated workflow.
        own_fields = [
            f for f in definition.get("entity_schema", {}).get("fields", []) if not f.get("source_states")
        ]
        keys_to_drop = [f.get("field") for f in own_fields if f.get("field") in keys]
        block_engine = {
            f.key.lower(): key_engine_type.get((b.schema_key, f.key.lower()), "")
            for b in type_blocks for f in b.fields
        }
        retyped = [
            f"{f.get('field')}: {f.get('type')} -> {block_engine[str(f.get('field')).lower()]}"
            for f in own_fields
            if f.get("field") in keys and block_engine.get(str(f.get("field")).lower()) not in ("", None, f.get("type"))
        ]
        wanted = {b.method_id for b in type_blocks if b.method_id}
        # A topped-up block has (or, before apply, will have) a new version; a
        # workflow still pinned to the old one has not received the inherited
        # fields and must be re-published against the new version.
        pending_top_up = any(b.action == "top-up" and not b.top_up_applied for b in type_blocks)
        new_versions = {b.method_id: b.version_id for b in type_blocks if b.action == "top-up" and b.top_up_applied}

        def _state_pinned(state: dict[str, Any]) -> bool:
            refs = {r.get("method_id"): r.get("version_id") for r in state.get("method_refs", [])}
            if not wanted <= set(refs):
                return False
            return all(refs.get(mid) == vid for mid, vid in new_versions.items())

        already = (
            bool(wanted)
            and not pending_top_up
            and not keys_to_drop
            and all(_state_pinned(s) for s in definition.get("states", []))
        )
        draft = drafts.get(machine_name)
        if draft is None:
            draft_status = "none"
        elif draft == definition:
            draft_status = "same"
        else:
            draft_status = "differs"
        if already:
            action = "skip-already-pinned"
        elif draft_status == "differs" and not overwrite_drafts:
            action = "skip-draft-differs"
        else:
            action = "publish"
        plans.append(
            WorkflowPlan(
                org_id=org_id, machine_name=machine_name, active_row_id=row_id, active_version=version,
                entity_type=entity_type, states=states, blocks=[b.schema_key for b in type_blocks],
                keys_to_drop=keys_to_drop, draft_status=draft_status, action=action, retyped=retyped,
            )
        )
    return plans


def build_plan(
    engine, only_org: str | None, overwrite_drafts: bool, sync_plain_fields: set[str] = frozenset()
) -> list[OrgPlan]:
    plans: list[OrgPlan] = []
    with engine.connect() as conn:
        by_engine, kinds, engine_of = _catalogue(conn)
        orgs = conn.execute(
            sa.text(
                f'SELECT DISTINCT o.id, o.name FROM "{_schema()}".organizations o '
                f'JOIN "{_defs()}".entity_type_schema s ON s.organization_id = o.id AND s.is_active '
                + ("WHERE o.id = :org " if only_org else "")
                + "ORDER BY o.name"
            ),
            {"org": only_org} if only_org else {},
        ).all()
        for org_id, org_name in orgs:
            plan = OrgPlan(org_id=org_id, org_name=org_name)
            slots = _load_slots(conn, org_id, by_engine, plan)
            refs = [s for s in slots if s.encoding == "ref"]
            real = [s for s in slots if s.encoding != "ref"]
            # Migratable __ref__ slots join the plan like any other slot: they
            # need a library field and a place in their Form's block.
            real.extend(_plan_refs(conn, org_id, refs, plan))
            fields = _plan_fields(real, _existing_fields(conn, org_id), kinds, plan)
            plan.fields = [fields[k] for k in sorted(fields)]
            plan.blocks = _plan_blocks(conn, org_id, real, plan, sync_plain_fields=sync_plain_fields)
            code_by_shape = {(fp.key.lower(), sp.shape_key): sp.code for fp in fields.values() for sp in fp.shapes}
            plan.key_engine_type = {
                (b.schema_key, bf.key.lower()): engine_of.get(code_by_shape.get((bf.key.lower(), bf.shape_key), ""), "")
                for b in plan.blocks for bf in b.fields
                if bf.inherited_from is None  # read-only on the record; its type is not a correction
            }
            plan.workflows = _plan_workflows(conn, org_id, plan.blocks, overwrite_drafts, plan.key_engine_type)
            plans.append(plan)
    return plans


# ─── apply (through the application services) ────────────────────────────────


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
    return (
        by_name["FieldLibraryServiceManager"],
        by_name["MethodLibraryServiceManager"],
        by_name["WorkflowServiceManager"],
    )


def _apply_fields(field_svc, plan: OrgPlan) -> None:
    from exceptions import ValidationError
    from field_library.models.request import FieldCreateRequest, FieldVersionCreateRequest

    actor = _actor(plan.org_id)
    for fp in plan.fields:
        try:
            pending = [sp for sp in fp.shapes if sp.action == "create"]
            if fp.library_field_id is None:
                first, pending = pending[0], pending[1:]
                created = field_svc.create_field_for_actor(
                    actor,
                    FieldCreateRequest(
                        name=fp.name, field_key=fp.key, field_type=first.code,
                        description=first.description, settings=first.settings,
                    ),
                )
                fp.library_field_id = created.identity.library_field_id
                first.version_id = created.version.version_id
            for sp in pending:
                version = field_svc.create_version_for_actor(
                    actor, fp.library_field_id,
                    FieldVersionCreateRequest(description=sp.description, settings=sp.settings, field_type=sp.code),
                )
                sp.version_id = version.version_id
        except ValidationError as exc:
            plan.errors.append(f"field '{fp.key}': {exc}")


def _block_field_input(bf: BlockField, fields: dict[str, FieldPlan], bp: BlockPlan, plan: OrgPlan, position: int):
    """One MethodFieldInput for a planned block field, or None (error recorded)."""
    from method_library.models.request import MethodFieldInput

    fp = fields.get(bf.key.lower())
    if fp is None or fp.library_field_id is None:
        plan.errors.append(f"block '{bp.schema_key}': field '{bf.key}' has no library field; block skipped")
        return None
    sp = next((s for s in fp.shapes if s.shape_key == bf.shape_key), None)
    if sp is None or sp.version_id is None:
        plan.errors.append(f"block '{bp.schema_key}': field '{bf.key}' has no version for its shape; block skipped")
        return None
    inherited: dict[str, Any] = {}
    if bf.inherited_from is not None:
        source_entity, source_field = bf.inherited_from
        # The block field keeps the legacy target key (the library field's key);
        # the source is declared separately, so `account_legal_name` can still
        # read `account.legal_name`.
        inherited = {
            "ownership": "inherited",
            "source_entity_type": source_entity,
            "source_field_key": source_field,
        }
    return MethodFieldInput(
        library_field_id=fp.library_field_id, version_id=sp.version_id, label=bf.label,
        placeholder=bf.placeholder, required=bf.required, position=position, **inherited,
    )


def _carry_existing_field(existing) -> Any:
    """A MethodFieldInput that re-states one existing block field unchanged,
    version pin and inheritance markers included. Omitting `version_id` would
    silently re-pin to the field's latest version; omitting `ownership` would
    turn an inherited field back into an entered one."""
    from method_library.models.request import MethodFieldInput

    return MethodFieldInput(
        library_field_id=existing.library_field_id, version_id=existing.field_version_id,
        label=existing.label, placeholder=existing.placeholder, required=existing.required,
        position=existing.position, inherit_from=existing.inherit_from,
        ownership=getattr(existing, "ownership", None),
        source_entity_type=existing.source_entity_type, source_field_key=existing.source_field_key,
    )


def _apply_blocks(method_svc, plan: OrgPlan, fields: dict[str, FieldPlan]) -> None:
    from exceptions import ValidationError
    from method_library.models.request import MethodCreateRequest, MethodFieldListUpdateRequest

    actor = _actor(plan.org_id)
    for bp in plan.blocks:
        if bp.action in ("reuse", "top-up"):
            try:
                with_fields = method_svc.get_method_with_fields_for_actor(actor, bp.method_id)
                bp.version_id = with_fields.version.version_id
            except Exception as exc:  # noqa: BLE001
                plan.errors.append(f"block '{bp.schema_key}': existing method unreadable: {exc}")
                continue
            if bp.action != "top-up":
                continue
            # Top-up: existing fields carried through as they are, the missing
            # inherited fields appended after them. One replace, one new version.
            carried = [_carry_existing_field(f) for f in sorted(with_fields.fields, key=lambda f: f.position)]
            present = {f.field_key.lower() for f in with_fields.fields}
            additions = []
            for bf in bp.fields:
                # top_up_keys is the plan's own decision (inherited, always;
                # plain, only when its schema_key was named on
                # --sync-plain-fields) - the single source of truth here
                # rather than re-deriving it from bf.inherited_from, so the
                # two never drift apart.
                if bf.key not in bp.top_up_keys or bf.key.lower() in present:
                    continue
                inp = _block_field_input(bf, fields, bp, plan, position=len(carried) + len(additions))
                if inp is None:
                    additions = None
                    break
                additions.append(inp)
            if not additions:
                continue
            try:
                updated = method_svc.replace_method_fields_for_actor(
                    actor, bp.method_id, MethodFieldListUpdateRequest(fields=[*carried, *additions])
                )
                bp.version_id = updated.version.version_id
                bp.top_up_applied = True
            except ValidationError as exc:
                plan.errors.append(f"block '{bp.schema_key}' top-up: {exc}")
            continue
        inputs = []
        for bf in bp.fields:
            inp = _block_field_input(bf, fields, bp, plan, position=bf.position)
            if inp is None:
                inputs = None
                break
            inputs.append(inp)
        if inputs is None:
            continue
        try:
            created = method_svc.create_method_for_actor(
                actor,
                MethodCreateRequest(
                    name=bp.name, description=bp.description, fields=inputs, entity_types=[bp.entity_type]
                ),
            )
            bp.method_id = created.identity.method_id
            bp.version_id = created.version.version_id
        except ValidationError as exc:
            plan.errors.append(f"block '{bp.schema_key}': {exc}")


def _apply_workflows(workflow_svc, plan: OrgPlan) -> None:
    from workflow.models.interface import StateMachineDefinition
    from workflow.models.request import WorkflowDraftSeedRequest, WorkflowPublishRequest

    actor = _actor(plan.org_id)
    blocks_by_type: dict[str, list[BlockPlan]] = defaultdict(list)
    for b in plan.blocks:
        if b.method_id:
            blocks_by_type[b.entity_type].append(b)
    for wp in plan.workflows:
        if wp.action != "publish":
            continue
        type_blocks = blocks_by_type.get(wp.entity_type, [])
        if not type_blocks:
            wp.result = "no block created for this entity type"
            continue
        try:
            active = workflow_svc.workflow_db.get_active_state_machine(
                organization_id=plan.org_id, machine_name=wp.machine_name
            )
            if active is None:
                wp.result = "no active version found"
                continue
            definition = active.definition.model_dump(mode="json")
            # Same exclusion as the planning pass above: don't drop a field on
            # the belief a reused block covers it when `missing_plain_keys`
            # says it does not.
            keys = {
                f.key for b in type_blocks for f in b.fields if f.key not in b.missing_plain_keys
            }
            definition["entity_schema"]["fields"] = [
                f for f in definition["entity_schema"]["fields"]
                if f.get("field") not in keys or f.get("source_states")
            ]
            repin = {b.method_id: b.version_id for b in type_blocks if b.action == "top-up" and b.top_up_applied}
            for state in definition["states"]:
                refs = state.setdefault("method_refs", [])
                for ref in refs:
                    # Move a pin to the topped-up block version so the appended
                    # inherited fields reach this workflow's schema. Other pins
                    # are left exactly where they are: pins are stable by design.
                    if ref.get("method_id") in repin:
                        ref["version_id"] = repin[ref["method_id"]]
                present = {r.get("method_id") for r in refs}
                for b in type_blocks:
                    if b.method_id not in present:
                        refs.append({"method_id": b.method_id, "version_id": b.version_id})
            new_definition = StateMachineDefinition.model_validate(definition)
            draft = workflow_svc.seed_workflow_draft_for_actor(actor, wp.machine_name, WorkflowDraftSeedRequest())
            published = workflow_svc.publish_workflow_for_actor(
                actor, draft.id, WorkflowPublishRequest(definition=new_definition)
            )
            wp.result = f"published v{published.state_machine.version}"
        except Exception as exc:  # noqa: BLE001
            wp.result = f"FAILED: {str(exc)[:400]}"
            plan.errors.append(f"workflow '{wp.machine_name}': {str(exc)[:400]}")


# ─── report ──────────────────────────────────────────────────────────────────


def _print_plan(plans: list[OrgPlan], applied: bool) -> None:
    mode = "APPLIED" if applied else "DRY RUN (nothing written)"
    print(f"\n=== Legacy Forms -> Field Library + Method Blocks: {mode} ===")
    tot = defaultdict(int)
    for p in plans:
        print(f"\n--- {p.org_name} ({p.org_id}) ---")
        new_fields = [f for f in p.fields if f.existing_field_id is None]
        versions = sum(1 for f in p.fields for s in f.shapes if s.action == "create")
        print(f"  library fields: {len(new_fields)} new, {len(p.fields) - len(new_fields)} existing; versions to create: {versions}")
        for f in p.fields:
            for n in f.notes:
                print(f"      {n}")
        creates = [b for b in p.blocks if b.action == "create"]
        top_ups = [b for b in p.blocks if b.action == "top-up"]
        print(
            f"  method blocks: {len(creates)} new, {len(p.blocks) - len(creates)} existing"
            + (f" ({len(top_ups)} to top up with inherited fields)" if top_ups else "")
        )
        for b in p.blocks:
            tag = b.action if not b.method_id else f"{b.action} {b.method_id[:8]}"
            inherited = sum(1 for f in b.fields if f.inherited_from is not None)
            detail = f"{len(b.fields)} fields" + (f", {inherited} inherited" if inherited else "")
            print(f"      [{tag}] '{b.name}' <- form {b.schema_key} ({b.entity_type}), {detail}")
            if b.top_up_keys:
                state = "appended" if b.top_up_applied else "to append"
                print(f"            inherited fields {state}: {', '.join(b.top_up_keys)}")
            if b.missing_plain_keys:
                print(
                    f"            note: plain fields in the Form but no longer in this block, left as is: "
                    f"{', '.join(b.missing_plain_keys)}"
                )
        print(f"  workflows: {len(p.workflows)}")
        for w in p.workflows:
            res = f" -> {w.result}" if w.result else ""
            print(
                f"      [{w.action}] {w.machine_name} v{w.active_version} ({w.entity_type}): "
                f"{len(w.states)} states, drop {len(w.keys_to_drop)} schema keys, draft={w.draft_status}{res}"
            )
            for line in w.retyped:
                print(f"            schema type corrected to the Form's type: {line}")
        if p.sibling_versions:
            print(f"  sibling-version fields ({len(p.sibling_versions)}):")
            for line in p.sibling_versions:
                print(f"      {line}")
        if p.deduplicated:
            print(f"  keys defined differently on two forms of one entity type, kept once ({len(p.deduplicated)}):")
            for line in p.deduplicated:
                print(f"      {line}")
        if p.name_collisions:
            print(f"  name collisions resolved ({len(p.name_collisions)}):")
            for line in p.name_collisions:
                print(f"      {line}")
        if p.converter_caveats:
            print(f"  pin-converter caveats ({len(p.converter_caveats)}):")
            for line in p.converter_caveats:
                print(f"      {line}")
        if p.ref_migrated:
            print(
                f"  __ref__ slots migrated as inherited block fields ({len(p.ref_migrated)}; "
                f"{p.ref_restored_count} restored, relation_metadata untouched):"
            )
            for line in p.ref_migrated:
                print(f"      {line}")
        if p.ref_skipped:
            print(f"  __ref__ slots NOT migrated ({len(p.ref_skipped)}):")
            for line in p.ref_skipped:
                print(f"      {line}")
        if p.skipped:
            print(f"  skipped slots ({len(p.skipped)}):")
            for line in p.skipped:
                print(f"      {line}")
        if p.errors:
            print(f"  ERRORS ({len(p.errors)}):")
            for line in p.errors:
                print(f"      {line}")
        tot["fields"] += len(new_fields)
        tot["versions"] += versions
        tot["blocks"] += len(creates)
        tot["publish"] += sum(1 for w in p.workflows if w.action == "publish")
        tot["skip_draft"] += sum(1 for w in p.workflows if w.action == "skip-draft-differs")
        tot["published"] += sum(1 for w in p.workflows if w.result.startswith("published"))
        tot["failed"] += sum(1 for w in p.workflows if w.result.startswith("FAILED"))
        tot["top_up"] += len(top_ups)
        tot["refs"] += len(p.ref_migrated)
        tot["refs_restored"] += p.ref_restored_count
        tot["refs_skipped"] += len(p.ref_skipped)
        tot["retyped"] += sum(1 for w in p.workflows for _ in w.retyped)
        tot["errors"] += len(p.errors)
    print(
        f"\nTotals: {tot['fields']} new fields, {tot['versions']} versions, {tot['blocks']} new blocks, "
        f"{tot['top_up']} blocks topped up, "
        f"{tot['publish']} workflows to publish ({tot['skip_draft']} skipped: draft differs), "
        f"{tot['refs']} __ref__ slots migrated as inherited ({tot['refs_restored']} restored, "
        f"{tot['refs_skipped']} not migrated), {tot['retyped']} schema types corrected, {tot['errors']} errors"
        + (f"; published {tot['published']}, failed {tot['failed']}" if applied else "")
    )


def _dump_report(plans: list[OrgPlan], path: str, applied: bool) -> None:
    def enc(o):
        if hasattr(o, "__dataclass_fields__"):
            d = {k: getattr(o, k) for k in o.__dataclass_fields__}
            for internal in ("entry", "slots", "key_engine_type"):
                d.pop(internal, None)
            return d
        return str(o)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"applied": applied, "organizations": plans}, fh, default=enc, indent=2)
    print(f"report written to {path}")


# ─── main ────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="Write through the application services. Default is a dry run.")
    ap.add_argument("--org", default=None, help="Limit to one organization id.")
    ap.add_argument("--report", default=None, help="Also write a JSON report to this path.")
    ap.add_argument(
        "--overwrite-drafts", action="store_true",
        help="Publish even when a workflow's version-0 draft differs from its active definition (the draft is overwritten).",
    )
    ap.add_argument(
        "--sync-plain-fields", default=None,
        help=(
            "Comma-separated Form schema_keys whose block should have a plain "
            "field re-added if the Form now has one the block does not - the "
            "same top-up mechanism used for inherited fields, opt-in and named "
            "explicitly because a missing plain field is normally left alone "
            "(see the module docstring: a human may have removed it on "
            "purpose). Use this after adding a field to one of these Forms by "
            "hand or with a data_repairs/ script."
        ),
    )
    args = ap.parse_args()

    sync_plain_fields = set(
        filter(None, (args.sync_plain_fields or "").split(","))
    )
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    plans = build_plan(engine, args.org, args.overwrite_drafts, sync_plain_fields=sync_plain_fields)

    if args.apply:
        field_svc, method_svc, workflow_svc = _services()
        for plan in plans:
            _apply_fields(field_svc, plan)
            _apply_blocks(method_svc, plan, {f.key.lower(): f for f in plan.fields})
            # method ids are only known now; recompute the already-pinned check
            plan.workflows = _plan_workflows_after_blocks(engine, plan, args.overwrite_drafts)
            _apply_workflows(workflow_svc, plan)

    _print_plan(plans, args.apply)
    if args.report:
        _dump_report(plans, args.report, args.apply)
    return 1 if any(p.errors for p in plans) else 0


def _plan_workflows_after_blocks(engine, plan: OrgPlan, overwrite_drafts: bool) -> list[WorkflowPlan]:
    with engine.connect() as conn:
        return _plan_workflows(conn, plan.org_id, plan.blocks, overwrite_drafts, plan.key_engine_type)


if __name__ == "__main__":
    sys.exit(main())
