#!/usr/bin/env python3
"""
Schema-drift reconciliation report for the modular_backend platform.

The checks below exist because the schema has no enforcement on a few
free-text references: workflow_state_machines.entity_type (a varchar with no
FK to entity_types), method_library_method_entity_types.entity_type (same,
added by the new flow and deliberately unkeyed "to match workflows"), and the
field-mapping keys/values inside entity_type_relations.relation_metadata
(arbitrary JSON, no schema). Nothing at write time stops any of these from
pointing at something that doesn't exist - except the new flow's Method-pin
path, which validates its own writes. This script finds every place drift
has already happened, so it can be run repeatedly (e.g. against a fresh prod
dump) to catch new drift as it accumulates rather than discovering it ad hoc.

Usage:
    python3 reconciliation_report.py [--dbname audit_dump] [--host /var/run/postgresql]
    python3 reconciliation_report.py --dsn postgresql://user:pass@host:5432/db
    DATABASE_URL=postgresql://... python3 reconciliation_report.py      # inside the backend container

Connection precedence: --dsn, then DATABASE_URL when set (the app container
always has it, so no password juggling there), then --dbname/--host with the
usual PG* environment variables.
"""
import argparse
import json
import os
from collections import defaultdict

import psycopg2
import psycopg2.extras


def connect(dbname, host, dsn=None):
    dsn = dsn or os.environ.get("DATABASE_URL")
    if dsn:
        conn = psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://", 1))
    else:
        conn = psycopg2.connect(dbname=dbname, host=host)
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def extract_field_mappings(metadata):
    """relation_metadata mixes real field mappings ('from.field': 'to.field')
    with unrelated config keys (e.g. 'related_files', and the new flow's
    '_method_attribution' list). A real mapping's key looks like
    '<from_type>.<field>' and maps to a string '<to_type>.<field>'."""
    pairs = []
    for k, v in metadata.items():
        if not isinstance(v, str) or "." not in k or "." not in v:
            continue
        pairs.append((k.split(".", 1)[1], v.split(".", 1)[1]))
    return pairs


def check_relation_field_mappings(cur):
    """For every active entity_type_relations declaration with a field
    mapping, check every REFERENCE-type instance of that relation: does the
    source record actually have the mapped field, and if the target also
    keeps its own copy, does it still match the source?"""
    cur.execute("""
        select r.organization_id, o.name as org, r.from_entity_type_id, r.to_entity_type_id,
               fet.name as from_type, tet.name as to_type, r.relation_type, r.relation_metadata
        from modular_backend_definitions.entity_type_relations r
        join modular_backend.organizations o on o.id = r.organization_id
        join modular_backend_definitions.entity_types fet on fet.entity_type_id = r.from_entity_type_id and fet.organization_id = r.organization_id
        join modular_backend_definitions.entity_types tet on tet.entity_type_id = r.to_entity_type_id and tet.organization_id = r.organization_id
        where r.deleted_at is null
    """)
    rel_defs = cur.fetchall()

    issues = []
    checked = 0
    missing = 0
    drift = 0

    for rd in rel_defs:
        pairs = extract_field_mappings(rd["relation_metadata"])
        if not pairs:
            continue

        cur.execute("""
            select er.relation_id, er.relation_type,
                   fe.entity_id as from_id, fe.data as from_data,
                   te.entity_id as to_id, te.data as to_data
            from modular_backend_runtime.entity_relations er
            join modular_backend_runtime.entities fe on fe.entity_id = er.from_entity_id and fe.organization_id = er.organization_id
            join modular_backend_runtime.entities te on te.entity_id = er.to_entity_id and te.organization_id = er.organization_id
            where er.organization_id = %s and fe.entity_type_id = %s and te.entity_type_id = %s
        """, (rd["organization_id"], rd["from_entity_type_id"], rd["to_entity_type_id"]))

        for inst in cur.fetchall():
            if inst["relation_type"] != "REFERENCE":
                continue  # SNAPSHOT rows are copied by design, not live-derived
            for src_field, tgt_field in pairs:
                checked += 1
                src_val = inst["from_data"].get(src_field, "__MISSING__")
                if src_val == "__MISSING__":
                    missing += 1
                    issues.append({
                        "check": "relation_field_mapping",
                        "severity": "high",
                        "org": rd["org"],
                        "detail": f"{rd['from_type']}.{src_field} -> {rd['to_type']}.{tgt_field}: "
                                  f"source field missing on live source record",
                        "from_id": inst["from_id"], "to_id": inst["to_id"],
                    })
                    continue
                if tgt_field in inst["to_data"] and inst["to_data"][tgt_field] != src_val:
                    drift += 1
                    issues.append({
                        "check": "relation_field_mapping",
                        "severity": "high",
                        "org": rd["org"],
                        "detail": f"{rd['from_type']}.{src_field} -> {rd['to_type']}.{tgt_field}: "
                                  f"DRIFT source={src_val!r} vs stored-copy={inst['to_data'][tgt_field]!r}",
                        "from_id": inst["from_id"], "to_id": inst["to_id"],
                    })

    return {
        "declarations_with_mappings": sum(1 for rd in rel_defs if extract_field_mappings(rd["relation_metadata"])),
        "instance_checks": checked,
        "missing_source_field": missing,
        "drift": drift,
        "issues": issues,
    }


def check_workflow_entity_types(cur):
    """workflow_state_machines.entity_type is a free-text varchar with no FK.
    Flag every currently-live workflow (is_active = true - workflows are
    versioned, and archived_at IS NULL alone also counts every superseded
    version row) whose entity_type doesn't match any real entity_types.name
    row in its own org."""
    cur.execute("""
        select o.name as org, w.id, w.machine_name, w.entity_type,
               (et.entity_type_id is not null) as exists
        from modular_backend.workflow_state_machines w
        join modular_backend.organizations o on o.id = w.organization_id
        left join modular_backend_definitions.entity_types et
          on et.organization_id = w.organization_id and et.name = w.entity_type
        where w.archived_at is null and w.is_active = true
    """)
    rows = cur.fetchall()
    total = len(rows)
    mismatched = [r for r in rows if not r["exists"]]

    by_value = defaultdict(lambda: {"count": 0, "orgs": set()})
    for r in mismatched:
        by_value[r["entity_type"]]["count"] += 1
        by_value[r["entity_type"]]["orgs"].add(r["org"])

    issues = [{
        "check": "workflow_entity_type",
        "severity": "medium" if r["entity_type"] == "entity" else "high",
        "org": r["org"],
        "detail": f"workflow '{r['machine_name']}' declares entity_type={r['entity_type']!r}, "
                  f"no matching entity_types row in this org",
        "from_id": r["id"], "to_id": None,
    } for r in mismatched]

    return {
        "active_total": total,
        "active_matched": total - len(mismatched),
        "active_mismatched": len(mismatched),
        "by_value": {k: {"count": v["count"], "orgs": sorted(v["orgs"])} for k, v in by_value.items()},
        "issues": issues,
    }


def check_method_entity_type_tags(cur):
    """New flow: method_library_method_entity_types.entity_type is free text
    with no FK to entity_types (by design, mirroring workflows). Flag every
    tag naming an entity type that doesn't exist in its org. Skipped cleanly
    when the table isn't there yet (a dump from before 202609010001)."""
    cur.execute("""
        select 1 from information_schema.tables
        where table_schema = 'modular_backend_definitions'
          and table_name = 'method_library_method_entity_types'
    """)
    if cur.fetchone() is None:
        return {"present": False, "total": 0, "mismatched": 0, "issues": []}

    cur.execute("""
        select o.name as org, m.name as method_name, t.entity_type,
               (et.entity_type_id is not null) as exists
        from modular_backend_definitions.method_library_method_entity_types t
        join modular_backend.organizations o on o.id = t.organization_id
        join modular_backend_definitions.method_library_methods m
          on m.method_id = t.method_id and m.organization_id = t.organization_id
        left join modular_backend_definitions.entity_types et
          on et.organization_id = t.organization_id and et.name = t.entity_type
    """)
    rows = cur.fetchall()
    mismatched = [r for r in rows if not r["exists"]]
    issues = [{
        "check": "method_entity_type_tag",
        "severity": "high",
        "org": r["org"],
        "detail": f"method '{r['method_name']}' is tagged for entity_type={r['entity_type']!r}, "
                  f"no matching entity_types row in this org",
        "from_id": None, "to_id": None,
    } for r in mismatched]
    return {"present": True, "total": len(rows), "mismatched": len(mismatched), "issues": issues}


def check_block_inherited_fields(cur):
    """Method-block-level inheritance (ownership='inherited' on a published
    workflow's entity_schema field). Unlike relation_metadata, the rule lives on
    the workflow version, so this walks every live workflow's schema and, for
    every record enrolled in it, checks the field the way the engine resolves
    it at read time: a REFERENCE link from a record of the source type must
    exist, the source record must have the source field, and a value the
    record still stores under the target key (legacy write, before the write
    guard) must match the live source value or it is masked drift.

    Also flags a pin whose relation declaration is gone (it can never resolve)
    and a pin that disagrees with a live relation_metadata mapping for the same
    target key (the two mechanisms would fight over one field). Skipped cleanly
    on a dump from before 202609060001."""
    cur.execute("""
        select 1 from information_schema.columns
        where table_schema = 'modular_backend_definitions'
          and table_name = 'method_library_method_version_fields' and column_name = 'ownership'
    """)
    if cur.fetchone() is None:
        return {"present": False, "workflows": 0, "pinned_fields": 0, "instance_checks": 0, "issues": []}

    # A record reads the schema of the version ROW it is enrolled in
    # (entity_state.workflow_id -> workflow_state_machines.id), and enrolments
    # never move when a newer version is published. So the versions that
    # matter are every row carrying inherited pins that is either the current
    # active version (new records land there) or still has records enrolled.
    cur.execute("""
        select w.id as workflow_id, w.organization_id, o.name as org, w.machine_name, w.entity_type,
               w.version, w.is_active, w.definition_json::jsonb as definition
        from modular_backend.workflow_state_machines w
        join modular_backend.organizations o on o.id = w.organization_id
        where w.archived_at is null and w.version >= 1
          and jsonb_path_exists(w.definition_json::jsonb, '$.entity_schema.fields[*] ? (@.ownership == "inherited")')
          and (w.is_active = true
               or exists (select 1 from modular_backend_runtime.entity_state es where es.workflow_id = w.id))
    """)
    workflows = cur.fetchall()

    # Coverage: for every active version with inherited pins, the records of
    # that workflow family enrolled in an OLDER version that does not carry the
    # pins. Those records do not see the block-level inherited value (or its
    # write guard) until they are re-enrolled or the rule also exists in
    # relation_metadata.
    cur.execute("""
        with active as (
            select w.id, w.organization_id, o.name as org, w.machine_name, w.entity_type
            from modular_backend.workflow_state_machines w
            join modular_backend.organizations o on o.id = w.organization_id
            where w.is_active = true and w.archived_at is null
              and jsonb_path_exists(w.definition_json::jsonb, '$.entity_schema.fields[*] ? (@.ownership == "inherited")')
        )
        select a.org, a.machine_name, a.entity_type,
               count(es.entity_id) as records_on_older_versions
        from active a
        join modular_backend.workflow_state_machines old
          on old.organization_id = a.organization_id and old.machine_name = a.machine_name and old.id <> a.id
          and not jsonb_path_exists(old.definition_json::jsonb, '$.entity_schema.fields[*] ? (@.ownership == "inherited")')
        join modular_backend_runtime.entity_state es on es.workflow_id = old.id
        join modular_backend_runtime.entities e on e.entity_id = es.entity_id and e.archived_at is null
        group by a.org, a.machine_name, a.entity_type
        order by 4 desc
    """)
    uncovered = cur.fetchall()

    cur.execute("""
        select r.organization_id, fet.name as from_type, tet.name as to_type,
               r.from_entity_type_id, r.to_entity_type_id, r.relation_type, r.relation_metadata
        from modular_backend_definitions.entity_type_relations r
        join modular_backend_definitions.entity_types fet on fet.entity_type_id = r.from_entity_type_id
        join modular_backend_definitions.entity_types tet on tet.entity_type_id = r.to_entity_type_id
        where r.deleted_at is null
    """)
    declarations = {}
    blanket = {}  # (org, to_type, target_field) -> (from_type, source_field)
    for d in cur.fetchall():
        declarations[(d["organization_id"], d["from_type"], d["to_type"])] = d
        for src_field, tgt_field in extract_field_mappings(d["relation_metadata"] or {}):
            blanket[(d["organization_id"], d["to_type"], tgt_field)] = (d["from_type"], src_field)

    issues = []
    pinned = 0
    checked = 0
    for wf in workflows:
        fields = [f for f in wf["definition"].get("entity_schema", {}).get("fields", []) if f.get("ownership") == "inherited"]
        for f in fields:
            pinned += 1
            src = f.get("source") or {}
            source_type, source_field, target = src.get("context_entity_type"), src.get("context_field"), f.get("field")
            decl = declarations.get((wf["organization_id"], source_type, wf["entity_type"]))
            base = f"workflow '{wf['machine_name']}' ({wf['entity_type']}) pins {target} <- {source_type}.{source_field}"
            if decl is None:
                issues.append({"check": "block_inherited_field", "severity": "high", "org": wf["org"],
                               "detail": f"{base}: no live relation from {source_type} to {wf['entity_type']}; can never resolve",
                               "from_id": wf["workflow_id"], "to_id": None})
                continue
            other = blanket.get((wf["organization_id"], wf["entity_type"], target))
            if other is not None and other != (source_type, source_field):
                issues.append({"check": "block_inherited_field", "severity": "high", "org": wf["org"],
                               "detail": f"{base}: relation_metadata maps the same key from {other[0]}.{other[1]}; two sources disagree",
                               "from_id": wf["workflow_id"], "to_id": None})
            # The provider is resolved the way the engine does it
            # (_find_link_for_declaration): the link row's relation_type must
            # match the declaration's and the provider record must be of the
            # declaration's from-type. Both conditions sit INSIDE the link
            # subquery so a record's link to some other provider type (a
            # request linked to a client AND a site) never surfaces as a
            # "no linked <type>" row. Oldest link wins, like the engine.
            cur.execute("""
                select te.entity_id as to_id, te.data as to_data, src.from_id, src.from_data
                from modular_backend_runtime.entity_state es
                join modular_backend_runtime.entities te on te.entity_id = es.entity_id and te.organization_id = es.organization_id
                left join lateral (
                    select fe.entity_id as from_id, fe.data as from_data
                    from modular_backend_runtime.entity_relations er
                    join modular_backend_runtime.entities fe
                      on fe.entity_id = er.from_entity_id and fe.organization_id = er.organization_id
                    where er.to_entity_id = te.entity_id and er.organization_id = te.organization_id
                      and er.relation_type = %s and fe.entity_type_id = %s
                    order by er.created_at asc
                    limit 1
                ) src on true
                where es.workflow_id = %s and es.organization_id = %s and te.archived_at is null
            """, (decl["relation_type"], decl["from_entity_type_id"], wf["workflow_id"], wf["organization_id"]))
            for inst in cur.fetchall():
                checked += 1
                if inst["from_id"] is None:
                    issues.append({"check": "block_inherited_field", "severity": "medium", "org": wf["org"],
                                   "detail": f"{base}: enrolled record has no linked {source_type}; field resolves blank",
                                   "from_id": None, "to_id": inst["to_id"]})
                    continue
                src_val = (inst["from_data"] or {}).get(source_field, "__MISSING__")
                if src_val == "__MISSING__":
                    issues.append({"check": "block_inherited_field", "severity": "high", "org": wf["org"],
                                   "detail": f"{base}: source field missing on linked {source_type} record",
                                   "from_id": inst["from_id"], "to_id": inst["to_id"]})
                    continue
                stored = (inst["to_data"] or {}).get(target, "__MISSING__")
                if stored != "__MISSING__" and stored != src_val:
                    issues.append({"check": "block_inherited_field", "severity": "medium", "org": wf["org"],
                                   "detail": f"{base}: record still stores {stored!r} under the key; masked by live value {src_val!r}",
                                   "from_id": inst["from_id"], "to_id": inst["to_id"]})
    return {
        "present": True,
        "workflows": len(workflows),
        "active_workflows": sum(1 for w in workflows if w["is_active"]),
        "pinned_fields": pinned,
        "instance_checks": checked,
        "uncovered": [dict(u) for u in uncovered],
        "uncovered_records": sum(u["records_on_older_versions"] for u in uncovered),
        "issues": issues,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbname", default="audit_dump")
    ap.add_argument("--host", default="/var/run/postgresql")
    ap.add_argument("--dsn", default=None, help="Full connection URL; overrides DATABASE_URL and --dbname/--host.")
    args = ap.parse_args()

    cur = connect(args.dbname, args.host, args.dsn)

    rel = check_relation_field_mappings(cur)
    wf = check_workflow_entity_types(cur)
    tags = check_method_entity_type_tags(cur)
    block = check_block_inherited_fields(cur)

    print("=" * 78)
    print("RECONCILIATION REPORT")
    print(f"database: {args.dsn or os.environ.get('DATABASE_URL') or args.dbname}".split("@")[-1])
    print("=" * 78)

    print("\n--- Check 1: entity_type_relations field mappings (relation_metadata) ---")
    print(f"Relation declarations with a real field mapping: {rel['declarations_with_mappings']}")
    print(f"REFERENCE-instance x mapping checks performed:    {rel['instance_checks']}")
    print(f"  source field missing on live source record:     {rel['missing_source_field']}")
    print(f"  stored-copy DRIFT from live source value:        {rel['drift']}")

    print("\n--- Check 2: workflow_state_machines.entity_type (free text, no FK), live versions only ---")
    print(f"Live workflow definitions (is_active): {wf['active_total']}")
    print(f"  matching a real entity_type:         {wf['active_matched']}")
    if wf["active_total"]:
        print(f"  matching NOTHING in this org:        {wf['active_mismatched']}  "
              f"({wf['active_mismatched'] / wf['active_total']:.0%} of live workflows)")
    for val, info in sorted(wf["by_value"].items(), key=lambda kv: -kv[1]["count"]):
        print(f"    entity_type={val!r}: {info['count']} workflows across {len(info['orgs'])} org(s): {', '.join(info['orgs'])}")

    print("\n--- Check 3: method_library_method_entity_types.entity_type (free text, no FK) ---")
    if not tags["present"]:
        print("table not present in this database (pre-202609010001) - skipped")
    else:
        print(f"Method -> entity type tags: {tags['total']}")
        print(f"  naming NOTHING in this org: {tags['mismatched']}")

    print("\n--- Check 4: method-block inherited fields (ownership='inherited' on live workflow schemas) ---")
    if not block["present"]:
        print("ownership column not present in this database (pre-202609060001) - skipped")
    else:
        print(f"Workflow versions pinning inherited block fields: {block['workflows']} "
              f"({block['active_workflows']} currently active; a record reads the version it is enrolled in)")
        print(f"  inherited fields pinned:                     {block['pinned_fields']}")
        print(f"  enrolled-record x field checks performed:    {block['instance_checks']}")
        print(f"  issues:                                      {len(block['issues'])}")
        print(f"  records enrolled in an OLDER version without the pins (not covered): {block['uncovered_records']}")
        for u in block["uncovered"]:
            print(f"    {u['org']} / {u['machine_name']} ({u['entity_type']}): {u['records_on_older_versions']} records")

    all_issues = rel["issues"] + wf["issues"] + tags["issues"] + block["issues"]
    print(f"\n--- All {len(all_issues)} issues (JSON lines) ---")
    for i in all_issues:
        print(json.dumps(i, default=str))

    cur.connection.close()


if __name__ == "__main__":
    main()
