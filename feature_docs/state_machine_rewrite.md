# State Machine Rewrite — Entity Model & Schema Convention

**Status:** In progress — `definitions.entity_types` and `runtime.entities` landed on branch `state_machine_rewrite`; rest of Wave 1 pending
**Owner:** Dhiraj
**Last updated:** 2026-05-03
**Scope:** modular_backend only (no prod data — greenfield restructure window)

---

## 1. Why this document

The modular_backend's state machine has two structural problems that compound each other:

1. **The entity model is wrong.** Identity, data, and state pointer are crammed into one row (`workflow_entity_states`). There is no `entities` table, no `entity_relations`, no per-entity event log. Data is TEXT, not JSONB. One entity cannot live in multiple workflows. Entities cannot exist outside a workflow.
2. **There's no naming convention separating definitions from runtime.** Configuration tables (workflow shapes, entity-type schemas) and runtime tables (entity instances, transition logs) sit side-by-side with no signal of which is which. Debugging, analytics, backups, and access control all suffer.

This document proposes fixing both at once. Now is the right moment because there is **no production data on modular_backend** — `app/` is the production backend, modular_backend is pre-launch. Every later moment is more expensive.

---

## 2. Goals & non-goals

**Goals**

- Establish a clear naming convention via Postgres schemas: `definitions`, `runtime`, `audit`.
- Split the entity model into four tables matching the design doc: `entities`, `entity_state`, `entity_relations`, `entity_events`.
- Add a canonical entity-type registry so "Candidate" is defined once, not embedded in each workflow.
- Unlock: entities exist outside workflows, one entity in many workflows, cross-entity relationships, per-entity audit timeline, JSONB queries on entity data.
- Rename existing modular tables (`workflow_state_machines`, `workflow_entity_states`, etc.) into their target schemas.

**Non-goals**

- Migration of `app/` production data into modular_backend. That's a separate project.
- Building actions & triggers. Tracked in `actions_and_triggers.md` and is downstream of this work.
- Changing the public REST API contract. The reshape is backend-only.
- Multi-database, sharding, or other infra changes.

---

## 3. The naming convention: Postgres schemas

Three schemas to start, with a fourth (`projections`) reserved for read models.

```
definitions.*    rare-write, version-controlled, admin-edited (the "config")
runtime.*        high-write, app-managed (the "data")
audit.*          append-only, immutable (the "history")
projections.*    derived read models (deferred — used when read-side work lands)
```

### Why schemas, not table-name suffixes

| | Schema split | Table-name suffix (`_definitions`, `_runtime`) |
|---|---|---|
| Per-schema permissions (`GRANT … ON ALL TABLES IN SCHEMA …`) | One line | Regex matching, ad hoc |
| Backups (`pg_dump --schema=definitions`) | Built-in | Manual table list |
| New table classification | Forced (must pick a schema) | Easy to forget |
| Table names | Stay short | Get long and stack awkwardly with domain prefixes |
| SQL readability | `runtime.entities` | `entity_runtime` |

Schemas also force a clear answer when a new table is added: "which bucket?" Without that forcing function, naming drift is inevitable (we're already living in the consequences of that drift).

### What goes where

| Schema | Tables (after this rewrite) |
|---|---|
| `definitions` | `entity_types`, `workflows`, `workflow_drafts`, `entity_schema_picklists` |
| `runtime` | `entities`, `entity_state`, `entity_relations` |
| `audit` | `entity_events`, `transition_attempts`, `definition_reports` |
| `projections` | _(deferred)_ |

Tables outside the state-machine domain (`organizations`, `users`, `roles`, `notifications`, `agent_*`, `mail_*`, etc.) stay where they are for now. This rewrite is scoped to state-machine concerns. They can be reorganized later in a separate pass.

---

## 4. The new data model

Five state-machine tables. Each shown with column shape and rationale.

### 4.1 `definitions.entity_types`

Canonical schema registry. Replaces today's pattern of embedding `entity_schema` inside each workflow's `definition_json`.

| Column | Type | Notes |
|---|---|---|
| `entity_type_id` | UUID PK | |
| `organization_id` | text/uuid | Tenant scope |
| `name` | text | E.g. `Candidate`, `Job`, `Application`. Unique per org. |
| `description` | text nullable | |
| `schema` | JSONB | Field definitions (name, type, required, enum_values, picklist_id). Same shape as today's `entity_schema` block. |
| `version` | int | Schema version |
| `is_active` | bool | |
| `created_at`, `updated_at` | timestamptz | |

Unique on `(organization_id, name, version)`. One active version per `(org, name)` at a time.

### 4.2 `definitions.workflows`

Replaces `workflow_state_machines`. Same shape, renamed for clarity.

| Column | Type | Notes |
|---|---|---|
| `workflow_id` | UUID PK | |
| `organization_id` | text/uuid | |
| `machine_key` | text | |
| `name` | text | |
| `description` | text nullable | |
| `entity_type_id` | UUID FK → `definitions.entity_types` | **New: hard FK** instead of soft-link by string |
| `version` | int | |
| `is_active` | bool | |
| `definition_json` | JSONB | Workflow DSL: states, transitions, guards |
| `created_at` | timestamptz | |

The hard FK to `entity_types` is the structural fix. Today the modular DSL embeds the entity schema; after the rewrite, the workflow references the canonical registry.

### 4.3 `runtime.entities`

The instance table. One row per real-world thing being tracked.

| Column | Type | Notes |
|---|---|---|
| `entity_id` | UUID PK | |
| `organization_id` | text/uuid | |
| `entity_type_id` | UUID FK → `definitions.entity_types` | |
| `data` | **JSONB** | The entity's domain data (e.g. `{"name":"Alice","email":"alice@x.com"}`). Replaces `data_json` TEXT. |
| `owner_id` | text nullable | |
| `created_at`, `updated_at`, `archived_at` | timestamptz | Soft-delete via `archived_at` |

Indexes: `(organization_id, entity_type_id)`, GIN on `data`.

### 4.4 `runtime.entity_state`

State pointer. **Multiple rows allowed per `entity_id`** — one per workflow enrollment.

| Column | Type | Notes |
|---|---|---|
| `state_id` | UUID PK | **Synthetic ID, not entity_id** — allows multiple states per entity |
| `entity_id` | UUID FK → `runtime.entities` | |
| `workflow_id` | UUID FK → `definitions.workflows` | Hard FK to the specific version |
| `current_state` | text | |
| `state_version` | int | Optimistic-lock counter |
| `state_entered_at`, `last_transition_at` | timestamptz | |
| `sla_due_at` | timestamptz nullable | |

Unique on `(entity_id, workflow_id)` — one entity can be in many workflows but only one row per `(entity, workflow_version)`.

**No `data` column here.** Data lives once, in `runtime.entities`.

### 4.5 `runtime.entity_relations`

Graph edges between entities.

| Column | Type | Notes |
|---|---|---|
| `relation_id` | UUID PK | |
| `organization_id` | text/uuid | |
| `from_entity_id` | UUID FK → `runtime.entities` | |
| `to_entity_id` | UUID FK → `runtime.entities` | |
| `relation_type` | text | E.g. `APPLIED_TO`, `BELONGS_TO`, `HAS_OFFER` |
| `metadata` | JSONB nullable | |
| `created_at` | timestamptz | |

Indexes on both directions: `(from_entity_id, relation_type)` and `(to_entity_id, relation_type)`.

### 4.6 `audit.entity_events`

Per-entity immutable timeline.

| Column | Type | Notes |
|---|---|---|
| `event_id` | UUID PK | |
| `organization_id` | text/uuid | |
| `entity_id` | UUID FK → `runtime.entities` | |
| `event_type` | text | E.g. `entity.created`, `application.transitioned`, `offer.approved` |
| `actor_type` | enum | `HUMAN` / `AGENT` / `SYSTEM` / `INTEGRATION` |
| `actor_id` | text nullable | |
| `correlation_id` | UUID nullable | |
| `idempotency_key` | text nullable | |
| `payload` | JSONB | |
| `occurred_at` | timestamptz | |

Append-only. No update path.

### 4.7 `audit.transition_attempts`

Replaces the `transition_attempt` rows currently in `workflow_activity_log`. Separate table because semantics are different from entity events.

| Column | Type | Notes |
|---|---|---|
| `transition_attempt_id` | UUID PK | |
| `organization_id` | text/uuid | |
| `entity_id` | UUID FK → `runtime.entities` | |
| `workflow_id` | UUID FK → `definitions.workflows` | |
| `from_state` | text | |
| `to_state` | text | |
| `trigger` | text | |
| `actor_id`, `actor_role` | text nullable | |
| `status` | enum | `SUCCEEDED` / `BLOCKED` / `CONFLICT` |
| `failure_code` | text nullable | |
| `idempotency_key` | text nullable | |
| `inputs`, `outputs` | JSONB | |
| `guard_evaluations` | JSONB | |
| `occurred_at` | timestamptz | |

This is the "why didn't this transition?" debug table.

### 4.8 What happens to `workflow_activity_log`

Today it mixes `transition_attempt` and `task_executed` rows with a discriminator column. Post-rewrite:

- `transition_attempt` rows → `audit.transition_attempts`
- `task_executed` rows → reserved for actions/triggers work (out of scope here)

The current `workflow_activity_log` table is dropped after the migration.

---

## 5. Worked scenarios — old vs new

Same scenarios from the prior conversation, captured here as the canonical reference. All examples assume `org_id = ORG-1`.

### Scenario 1: Define the Candidate type

**OLD** (today's modular)

`workflow_state_machines.definition_json` (excerpt): `{"entity_type":"Candidate","entity_schema":{"fields":[...]}}` — type schema embedded per-workflow.

**NEW**

`definitions.entity_types`

| entity_type_id | name | schema |
|---|---|---|
| ET-1 | Candidate | `{"fields":[{"field":"name","type":"string"},{"field":"email","type":"email"}]}` |

### Scenario 2: Create Alice with no workflow

**OLD** Impossible. Entity creation requires a workflow.

**NEW**

`runtime.entities`

| entity_id | entity_type_id | data |
|---|---|---|
| E-101 | ET-1 | `{"name":"Alice","email":"alice@x.com"}` |

`runtime.entity_state` — empty for Alice.

### Scenario 3: Enroll Alice in ATS pipeline

**OLD**

`workflow_entity_states`

| entity_id | machine_name | current_state | data_json |
|---|---|---|---|
| E-101 | ats_pipeline | APPLIED | `{"name":"Alice",...}` |

One combined row.

**NEW**

`runtime.entity_state`

| state_id | entity_id | workflow_id | current_state |
|---|---|---|---|
| S-200 | E-101 | WF-1 | APPLIED |

`runtime.entities` row from Scenario 2 unchanged. Data lives only there.

### Scenario 4: Alice transitions to SCREENING

**OLD**

`workflow_entity_states` mutated: `current_state=SCREENING`, `state_version+=1`. Plus a row in `workflow_activity_log`.

**NEW**

`runtime.entity_state` mutated. Plus:

`audit.entity_events`

| event_id | entity_id | event_type | from_state | to_state |
|---|---|---|---|---|
| EV-300 | E-101 | application.transitioned | APPLIED | SCREENING |

`audit.transition_attempts`

| transition_attempt_id | entity_id | workflow_id | from_state | to_state | status |
|---|---|---|---|---|---|
| TA-400 | E-101 | WF-1 | APPLIED | SCREENING | SUCCEEDED |

### Scenario 5: Enroll Alice in a *second* workflow (referral program)

**OLD** Impossible — PK conflict on `entity_id` in `workflow_entity_states`.

**NEW**

`runtime.entity_state`

| state_id | entity_id | workflow_id | current_state |
|---|---|---|---|
| S-200 | E-101 | WF-1 (ats_pipeline) | SCREENING |
| **S-201** | **E-101** | **WF-2 (referral_program)** | **REFERRED** |

One entity, two state rows. PK is `state_id`, not `entity_id`. **This is the structural unlock.**

### Scenario 6: Alice applies to Job #42

**OLD** Nowhere to store. Best you can do is shove `applied_to_job_id` into `data_json`. No reverse query, no FK integrity.

**NEW**

`runtime.entities` (Job is its own entity)

| entity_id | entity_type_id | data |
|---|---|---|
| E-501 | ET-2 (Job) | `{"title":"Senior Eng"}` |

`runtime.entity_relations`

| relation_id | from_entity_id | to_entity_id | relation_type |
|---|---|---|---|
| R-700 | E-101 | E-501 | APPLIED_TO |

Bidirectional queries become trivial.

### Scenario 7: Alice's full timeline

**OLD** `SELECT * FROM workflow_activity_log WHERE entity_id='E-101'`. Mixed with task executions, workflow-scoped.

**NEW** `SELECT * FROM audit.entity_events WHERE entity_id='E-101' ORDER BY occurred_at`. Clean per-entity timeline across every workflow.

---

## 6. Implementation plan

Two execution waves. **Both designed together.** Either can ship independently if needed.

### Wave 1 — Greenfield additions (low risk)

Goal: land the schemas and the new tables in their final shape. No renaming of existing tables yet.

- Create Postgres schemas: `definitions`, `runtime`, `audit`.
- Create new tables: `definitions.entity_types`, `runtime.entities`, `runtime.entity_state`, `runtime.entity_relations`, `audit.entity_events`, `audit.transition_attempts`.
- Wire SQLAlchemy models with `__table_args__ = {"schema": "..."}`.
- Update `workflow/manager.py:create_entity_for_actor` to write to `runtime.entities` + `runtime.entity_state` (dual-write alongside legacy `workflow_entity_states`).
- Update transition execution to write `audit.entity_events` + `audit.transition_attempts`.
- Backfill existing modular `workflow_entity_states` rows → split into `runtime.entities` + `runtime.entity_state` rows. (No prod data, so this is a one-time script run on dev/staging.)
- `POST /entities/{id}/relations` and `GET /entities/{id}/relations` endpoints land here.

**Exits:** New entity model is in place. All entity reads/writes go through the new tables. The legacy `workflow_entity_states` and `workflow_activity_log` tables are still there but only read for backwards compatibility.

### Wave 2 — Rename existing tables into schemas (cleanup)

Goal: move the rest of the state-machine tables into the convention.

- Rename `workflow_state_machines` → `definitions.workflows`.
- Rename `workflow_entity_schema_picklists` → `definitions.entity_schema_picklists`.
- Rename `workflow_definition_reports` → `audit.definition_reports`.
- Drop `workflow_entity_states` (data already migrated in Wave 1).
- Drop `workflow_activity_log` (data already partitioned in Wave 1).
- Update all SQLAlchemy `__tablename__` and `__table_args__`.
- Update Alembic config (`version_table_schema` if needed).
- Drop the now-empty stub declarations in `entities/db_models.py`.

**Exits:** Every state-machine table lives in its proper schema. Single naming convention enforced. Stranded scaffolding removed.

### Wave order — pushback on user's proposal

The user's proposal: "first add entity relationships, then add the schemas."

**Recommendation: do them together** (as above). Reasoning:

- The new tables (`entities`, `entity_state`, `entity_relations`, `entity_events`) **must land in some schema**. Putting them in the current flat schema first and then moving them later is two migrations on the same tables for no benefit.
- Schema split for new tables is free — the cost is on existing tables, which we have to do anyway.
- Both changes touch the same surface (alembic, ORM, persistence layer). One coherent edit pass beats two.
- No prod data on modular_backend. Cost rises sharply once anything real is enrolled.

If hard sequencing is required, Wave 2 can be deferred — but the design is one document.

---

## 7. API impact

The frontend-facing REST API does **not** change shape. Specifically:

- `POST /entities` — same payload, same response. Backend now writes to `runtime.entities` + `runtime.entity_state`.
- `PATCH /entities/{id}` — same.
- `POST /entities/{id}/transitions` — same.
- **New: `POST /entities/{id}/relations`** and `GET /entities/{id}/relations` for managing entity relationships.
- **New: `POST /entities`** with no `machine_name` creates a "raw" entity (not yet enrolled). Existing payload with `machine_name` continues to work and creates entity + initial state in one call.
- **New: `POST /entities/{id}/enrollments`** to enroll an existing entity in an additional workflow.
- **New: `GET /entities/{id}/timeline`** returns rows from `audit.entity_events` for that entity.

All existing UI flows continue to function.

---

## 8. Open questions

1. **Server-generated vs. caller-provided entity IDs.** Today modular trusts the caller. Keep that, or generate server-side? (Recommend: server-generated UUID, with optional caller-provided `external_id` field for idempotency.)
2. **Cascade semantics on archive.** When an entity is archived (`archived_at` set), do its state rows freeze, archive too, or stay live? (Recommend: state rows stay live; the runtime treats archived entities as "no transitions allowed" but the state row is preserved for audit.)
3. **Multi-org entity relations.** Are cross-org relations ever valid? (Recommend: no. Enforce `from_entity.organization_id == to_entity.organization_id` at write time.)
4. **`entity_types` ownership.** Per-org only, or do we want platform-level templates? (Recommend: per-org for now. Templates can come later via the picklists table.)
5. **`workflow_id` vs `(machine_name, machine_version)` on `entity_state`.** Hard FK to `workflow_id` is cleaner but means migrating an entity to a new workflow version requires updating the FK. Soft-link by name+version preserves the current behavior. (Recommend: hard FK to a specific `workflow_id`. Migrating an entity to a new version is an explicit action, not implicit.)
6. **Where do `roles`, `users`, `notifications`, `agent_*` etc. go?** Leave alone in this rewrite. Future cleanup pass.
7. **Naming for the future actions/triggers tables.** Pin `audit.action_runs` ahead of that work so it lands in the right schema from day one.

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ORM boilerplate (`__table_args__ = {"schema": "..."}`) on every model | Low | One-time grep-and-update; convention enforced in code review |
| Alembic schema-aware migrations | Low | `version_table_schema` config; well-documented Postgres pattern |
| Cross-schema FK references | Low | Postgres handles natively |
| Rewrite scope creep ("while we're at it, let's also redo X") | **Medium** | Keep this doc tight to state-machine tables. Other domains explicitly out of scope. |
| Frontend regressions | Low | API contract unchanged |
| Eventual `app/` → modular migration must respect this new schema | **Medium** | Tracked separately. The new schema is the migration target. This rewrite lays the runway. |

---

## 10. Out of scope (explicit)

- `app/` to modular_backend data migration. Tracked separately.
- Actions & triggers feature. Tracked in `actions_and_triggers.md`. This rewrite is a precondition.
- Reorganizing non-state-machine tables (auth, notifications, agent, mail, integrations).
- Frontend changes beyond consuming the new endpoints.
- Performance optimization, sharding, partitioning.
- Read-side projections — deferred until that work is on the table.

---

## 11. Implementation status

Tracked as a sequence of commits on branch `state_machine_rewrite`.

### Landed

**Commit 1 — `definitions.entity_types` registry** *(prior session, already on branch)*
- Migration `2026_05_02_0004_add_entity_types`: creates `${app_schema}_definitions` schema and `entity_types` table with cross-schema FK to `organizations`.
- `EntityTypeModel` ORM with `__table_args__ = {"schema": _definitions_schema()}`.
- Pydantic models: `EntityType`, `EntityTypeCreateRequest`, `EntityTypeUpdateRequest`, `EntityTypeRecordResponse`, `EntityTypeRecordListResponse`.
- Manager methods + `_for_actor` variants for create / get / list / update.
- Controller routes (initial shape — UUID-keyed with `?organization_id=` query): `POST/GET /entity-types`, `GET/PUT /entity-types/{id}`.
- 9 endpoint tests against the (then-extant) in-memory model service.

**Commit 2 — `runtime.entities` + `/entity-records` CRUD** *(this session)*
- Migration `2026_05_02_0005_add_runtime_entities`: creates `${app_schema}_runtime` schema and `entities` table. Cross-schema FKs to `organizations` and `definitions.entity_types`. Indexes on `organization_id`, `entity_type_id`, and composite `(organization_id, entity_type_id, archived_at)`.
- `EntityRecordModel` ORM, `EntityRecord` Pydantic + request/response models.
- Manager: `create / get / list / update / archive_entity_record` + `_for_actor` variants.
- Controller: `POST/GET /entity-records`, `GET/PUT/DELETE /entity-records/{id}`. `DELETE` = soft archive via `archived_at`.
- 8 endpoint tests.

**Commit 3 — Legacy delete + entity-types reshape + agent-tool migration** *(this session)*
- Deleted 7 legacy routes: `/entities/entity-types` (POST), `/metadata_registry/entity-types` (POST + GET), `/entities/entity-types/{org}` (GET), `/metadata_registry/entity-types/{org}` (GET), `/entities/lifecycle/resolve`, `/metadata_registry/lifecycle/resolve`, `/metadata_registry/funnel/resolve`.
- Deleted in-memory entity_type stub: `_entity_type_registry` dict, `upsert_entity_type`, `get_entity_type`, `list_entity_types`, `EntityTypeRecord` dataclass — the data-lossy bug that motivated this rewrite.
- Deleted legacy models/manager methods: `EntityTypeContract`, `FunnelResolution`, `MetadataLookupPort.get_entity_type`, `UpsertEntityTypeRequest`, `ResolveFunnelRequest`, legacy `EntityTypeResponse` / `EntityTypeListResponse` / `FunnelResolutionResponse`, plus `resolve_funnel` / `resolve_lifecycle` + actor variants.
- Reshaped Commit-1 endpoints: `/entity-types/{name}` path (name not UUID), `organization_id` derived from actor (no query). Added `DELETE /entity-types/{name}` for soft archive (`is_active=false`).
- Migrated agent tool wiring: `tools/manager.py:_execute_list_entity_types` calls `list_entity_type_records`. `tests/agent_module/fakes.py` and `tests/tools_module/fakes.py` return `EntityTypeRecordResponse`.

**Commit 4 — Postgres-only model service** *(this session)*
- `EntitiesModelService` is now Postgres-only. Constructor raises `PersistenceError` if `database_service_manager` is absent or missing `postgres_db_service`.
- Deleted: `MemoryEntityType`, `MemoryEntityRecord`, `_use_memory()`, `_memory_entity_type_by_name`. The 10 CRUD methods now have one path each (~120 lines removed).
- Added `entities_db_service_manager` session-scoped pytest fixture in `tests/conftest.py`: connects to dev Postgres with `search_path=<app_schema>,public`, seeds `test-org-1` / `test-org-2`, autouse per-test cleanup of `_runtime.entities` and `_definitions.entity_types` rows.
- Tests now exercise real cross-schema FKs, `IntegrityError → ConflictError → 409`, JSON round-trips.

**Commit 5 — Register `entity_record` in auth permission matrix** *(this session, bug fix)*
- Caught during live smoke: entity-records routes 403'd in production with `"permission not configured"`. Tests passed because the test's `_AlwaysAllowAuth` short-circuits.
- Added `("entity_record", "read"|"write")` to `_PERMISSION_MATRIX` in `auth/manager.py`. Renamed the resource string in `entities/manager.py` from `"entity_records"` (plural) to `"entity_record"` (singular, to match the matrix).

### Pending (Wave 1 remainder)

- `runtime.entity_state` table — multi-workflow enrollment with synthetic `state_id` PK. **The structural unlock** (one entity in many workflows).
- `runtime.entity_relations` table — graph edges between entities.
- `audit` schema + `audit.entity_events` table — per-entity immutable timeline.
- `audit.transition_attempts` table — replaces the `transition_attempt` half of `workflow_activity_log`.
- Rewire `workflow/manager.py:create_entity_for_actor` to write `runtime.entities` + `runtime.entity_state` (dual-write alongside legacy `workflow_entity_states` until Wave 2).
- Rewire transition execution to emit `audit.entity_events` + `audit.transition_attempts`.
- Endpoints: `POST/GET /entities/{id}/relations`, `POST /entities/{id}/enrollments`, `GET /entities/{id}/timeline`.
- Backfill script: existing `workflow_entity_states` → split into `runtime.entities` + `runtime.entity_state`.

### Pending (Wave 2 — renames)

- Rename `workflow_state_machines` → `definitions.workflows` (add hard FK to `definitions.entity_types`).
- Rename `workflow_entity_schema_picklists` → `definitions.entity_schema_picklists`.
- Rename `workflow_definition_reports` → `audit.definition_reports`.
- Drop `workflow_entity_states` (post-backfill).
- Drop `workflow_activity_log` (post-Wave-1 partition).
- Drop legacy ORM stubs in `entities/db_models.py` (`Entity`, `EntityRelation`, `EntityState`, `EntityEvent`).

### Follow-up cleanup (separate PRs, identified during PR2a/b)

- **Role-matrix cleanup.** `_PERMISSION_MATRIX` currently sprinkles `recruiter` (an ATS-specific role) across every generic platform resource (organization, comment, notification, document, metadata, workflow, projection, integration). Audit + replace with platform-generic roles.
- **Auth-as-controller-dependency refactor.** Move `_authorize_actor_operation` out of manager `_for_actor` methods and into FastAPI `Depends`. Halves the manager surface (~10 `_for_actor` variants → 0). Sweep across `entities`, `forms`, and any other manager with the pattern.
- **Strip in-memory paths from other modules.** Same playbook applied here for `entities`. Candidates: `forms`, `auth`, `agent`. Each ~30% smaller.
- **Form config DB-backed.** `_form_config_registry` is the only remaining in-process dict in `EntitiesModelService`, kept because `forms/manager.py` delegates to it. Rewrite when forms gets its own persistence rewrite.
- **Reject entity_record creation against archived entity_type.** Cross-schema FK only checks the row exists, not `is_active`. Needs an explicit guard in `create_entity_record`.
- **Drop the now-vestigial `MetadataLookupPort` Protocol** in `entities/models/interface.py` (only `get_form_config` remains; no cross-module consumers).

---

## 12. Test report

**Last run:** 2026-05-03, against `state-machine-modular-modular-db-1` (Postgres 16) and `state-machine-modular-modular-backend-1` (uvicorn).

### Automated tests

| Suite | Count | Result | Backing |
|---|---|---|---|
| `tests/test_entity_types_registry.py` | 10 | ✅ pass | Real Postgres |
| `tests/test_entity_records.py` | 8 | ✅ pass | Real Postgres |
| **Total** | **18** | **18/18** | 1.22s |

Tests now exercise real Postgres via the `entities_db_service_manager` conftest fixture: cross-schema FKs, `IntegrityError → ConflictError → 409` translation, JSON column round-trips, soft-delete semantics, and multi-tenant isolation are all under test.

Pre-existing baseline failures in `tests/agent_module/*` and `tests/tools_module/test_tools_manager.py` were verified by stashing the PR2 changes and re-running on baseline — same failures, unrelated (`actor_str` NameError in `tools/manager.py:782`, missing DB-required setup in agent tests).

### Manual smoke (live container)

Hit each endpoint via `curl` against `http://localhost:8001/v1/api`:

| # | Endpoint | Expectation | Result |
|---|---|---|---|
| 1 | `POST /entity-types` (admin, no `organization_id` in body) | 201, org from header | ✅ |
| 2 | `POST` duplicate `(org, name, version)` | 409 | ✅ |
| 3 | `POST` as viewer role | 403 | ✅ |
| 4 | `GET /entity-types` (no query param) | 200, scoped to actor's org | ✅ |
| 5 | `GET /entity-types/{name}` | 200 | ✅ |
| 6 | `GET /entity-types/{name}` cross-org | 404 | ✅ |
| 7 | `PUT /entity-types/{name}` | 200, `updated_at` advanced | ✅ |
| 8 | `DELETE /entity-types/{name}` | 200, `is_active=false` (soft) | ✅ |
| 9 | `POST /entity-records` | 201 | ✅ *(after auth fix)* |
| 10 | `GET /entity-records?organization_id=…` | 200 | ✅ |
| 11 | `GET /entity-records?organization_id=…&entity_type_id=…` filter | 200, filtered | ✅ |
| 12 | `GET /entity-records/{id}` | 200 | ✅ |
| 13 | `GET /entity-records/{id}` cross-org | 404 | ✅ |
| 14 | `PUT /entity-records/{id}` | 200 | ✅ |
| 15 | `DELETE /entity-records/{id}` | 200, `archived_at` set | ✅ |
| 16 | `GET /entity-records` excludes archived by default | active count = 0 | ✅ |
| 17 | `GET /entity-records?include_archived=true` | total count = 1 | ✅ |
| 18-24 | All 7 deleted legacy routes | 404/405 | ✅ |

### Bugs caught during smoke (and fixed)

1. **Auth resource not registered.** `entity-records` routes were 403'ing in production with `permission not configured`. Tests passed because `_AlwaysAllowAuth` short-circuits. Root cause: I'd named the auth resource string `"entity_records"` (plural) and never added it to `_PERMISSION_MATRIX` in `auth/manager.py`. Fixed by adding `("entity_record", "read"/"write")` to the matrix and renaming the resource string to singular in `entities/manager.py` (5 occurrences).

   Lesson: live smoke against the real auth stack catches what `_AlwaysAllowAuth` doesn't. Worth adding a minimal test that constructs the production `auth_service_manager` and verifies a happy-path call for any new resource string.

### Known issues (not caused by this rewrite, but worth tracking)

- `GET /openapi.json` returns 500 (pydantic `AgentDefinitionResponse not fully defined`) — pre-existing in agent module, unrelated.
- `tools/manager.py:782` references `actor_str` without importing it. Causes 1 test failure in `tests/tools_module/test_tools_manager.py`. Pre-existing on baseline.
- `tests/agent_module/*` tests need a `database_service_manager` for `ToolsModelService`. Pre-existing setup gap.

### Migration verified live

`alembic upgrade head` applied cleanly on the dev DB. Confirmed:

```
modular_backend
modular_backend_definitions   (entity_types)
modular_backend_runtime       (entities)
public
```

Cross-schema FKs from `runtime.entities` resolve to both `modular_backend.organizations(id)` and `modular_backend_definitions.entity_types(entity_type_id)`. Indexes (`pk_entities`, `ix_entities_entity_type_id`, `ix_entities_org_type_active`, `ix_entities_organization_id`) all created.
