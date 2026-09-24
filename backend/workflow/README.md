# Workflow API

## State Machines

### `GET /workflow-state-machines/status`
Returns workflow module health status. Frontend can call this before issuing any definition or runtime calls to confirm the module is wired and healthy.

**Response:** `WorkflowStatusResponse`

---

### `POST /workflow-state-machines/validate`
Validates a candidate state machine definition without persisting it. Runs structural validation and, when that passes, a dry-run simulation.

**Body:** `StateMachineValidateRequest`  
**Response:** `StateMachineValidationResponse`

---

### `POST /workflow-state-machines/workflow-paths`
Renders all discoverable workflow paths for a candidate definition. No persistence.

**Body:** `StateMachineValidateRequest`  
**Response:** `WorkflowPathsResponse`

---

### `POST /workflow-state-machines/draft`
Creates one empty workflow draft (version 0, inactive). Called when the user clicks "+" to start a new workflow. No validation runs at this stage.

**Body:** `WorkflowDraftCreateRequest` (optional)  
**Response:** `WorkflowDraftRecord` — `201 Created`

---

### `GET /workflow-state-machines`
Lists workflow rows with scope-aware filtering. Returns published rows, draft rows, or both.

**Query params:** `scope` (`published` | `draft` | `all`), `machine_name` (optional filter)  
**Response:** `WorkflowListResponse`

---

### `GET /workflow-state-machines/default-template`
Returns the canonical default state machine definition template. Frontend uses this as the starting body for validate and publish requests so field names, states, and transitions never need to be hardcoded on the client.

**Response:** `StateMachineDefinition`

---

### `GET /workflow-state-machines/{row_id}`
Fetches one exact workflow row by its primary-key row ID. Works for both draft (version 0) and published (version ≥ 1) rows.

**Path:** `row_id` — primary-key ID of the row  
**Response:** `WorkflowDraftRecord | StateMachineRecord`

---

### `PUT /workflow-state-machines/{row_id}/draft`
Overwrites the definition of an in-progress draft and runs structural validation. The draft is persisted even when invalid; validation issues are returned in the response for client-side guidance.

**Path:** `row_id` — primary-key ID of the draft row  
**Body:** `WorkflowDraftUpdateRequest`  
**Response:** `WorkflowDraftSaveResponse` (record, validation issues, is_valid flag)

---

### `DELETE /workflow-state-machines/{row_id}`
Deletes or resets one workflow row. Published rows are removed. Draft rows are reset to a blank definition when published siblings exist in the same family, or deleted outright when the draft is the only row.

**Path:** `row_id` — primary-key ID of the row  
**Response:** `WorkflowDraftRecord | StateMachineRecord` — the deleted or reset row

---

### `POST /workflow-state-machines/{row_id}/publish`
Publishes a draft row as a new persisted workflow version. Runs full validation and a dry-run before persisting.

**Path:** `row_id` — primary-key ID of the draft row  
**Body:** `WorkflowPublishRequest`  
**Response:** `StateMachinePublishResponse`

---

### `POST /workflow-state-machines/{machine_name}/draft`
Seeds a version-0 draft for an existing published workflow family. Used when a published workflow has no draft row and the user wants to start editing. Rejected with 409 if a draft already exists (response includes the existing `row_id` so the frontend can switch to the update path). Rejected with 404 if the family doesn't exist in the org. Rejected with 400 if the family has no published versions (use `POST /draft` for brand new workflows instead).

**Path:** `machine_name` — must match an existing published workflow family in the org  
**Body:** `WorkflowDraftSeedRequest` (optional — `definition`, `canvas_metadata`)  
**Response:** `WorkflowDraftRecord` — `201 Created`

---

### `GET /workflow-state-machines/{machine_name}/active`
Fetches the currently active version for a named workflow identity.

**Path:** `machine_name`  
**Response:** `StateMachineRecord`

---

### `GET /workflow-state-machines/{machine_name}/{version}`
Fetches one specific version of a workflow by exact version number.

**Path:** `machine_name`, `version` (int)  
**Response:** `StateMachineRecord`

---

### `GET /workflow-state-machines/{machine_name}/compare/{from_version}/{to_version}`
Diffs two versions of the same workflow. Returns added/removed states, added/removed transitions, guard changes, and required field changes. Nothing is mutated.

**Path:** `machine_name`, `from_version` (int), `to_version` (int)  
**Response:** `StateMachineVersionCompareResponse`

---

### `POST /workflow-state-machines/{machine_name}/{version}/validate`
Validates one persisted workflow version and stores the validation report.

**Path:** `machine_name`, `version` (int)  
**Response:** `DefinitionReport`

---

### `POST /workflow-state-machines/{machine_name}/{version}/activate`
Promotes one workflow version to active and deactivates the rest in the same family. Called after validation and compatibility checks pass.

**Path:** `machine_name`, `version` (int)  
**Response:** `StateMachineRecord`

---

### `POST /workflow-state-machines/{machine_name}/{version}/revert`
Re-activates an earlier workflow version. Newer versions are not deleted; the requested version re-runs safety checks before activation.

**Path:** `machine_name`, `version` (int)  
**Response:** `StateMachineRecord`

---

### `POST /workflow-state-machines/{machine_name}/{version}/dry-run-entity`
Dry-runs one entity snapshot against a specific workflow version. Returns the definition, validation report, and simulation summary. Nothing is persisted.

**Path:** `machine_name`, `version` (int)  
**Body:** `EntityDryRunRequest`  
**Response:** `EntityDryRunResponse`

---

### `POST /workflow-state-machines/{machine_name}/enrollments`
Enrolls an existing entity in the active version of a workflow. The entity record must already exist; this endpoint writes the enrollment row at the initial state and emits an `ENTITY_ENROLLED` event.

**Path:** `machine_name`  
**Body:** `WorkflowEnrollmentRequest`  
**Response:** `EntityState` — `201 Created`

---

### `GET /workflow-enrollments`
Returns an offset-paginated summary of enrollment rows for boards and lists. It
projects only requested card fields and can filter, sort, and page. Full entity
data remains on the entity-record detail endpoints.

**Paging:** `limit` (1–200, default 50) + `offset`. `has_more` reports whether
another page exists. There is no cursor — the kanban board's per-column infinite
scroll and the table's page numbers both page by offset over a stable
`enrollment_created_at DESC` ordering (newest enrollment first).

`offset` counts rows the caller may read, not raw rows, so every visible record
is reachable from some page and `total_count` counts the same set. How that is
enforced depends on the caller's read policy:

- Entity-type access → `entity_type_id IN (...)`.
- A row-level view condition on a field stored on the record itself →
  translated to a SQL predicate (`==`, `!=`, `in`), so the page is one query.
- A row-level condition on a field **inherited through an entity relation** →
  cannot be a predicate on that row (the inherited value wins over the stored
  one and lives on a different record), so those callers fall back to scanning
  raw rows and slicing after the policy runs. Since that condition is a
  property of the caller's roles across the whole org, a `LIMIT 1` probe first
  checks whether this request can reach a row of such a type at all; if not,
  the scan is skipped.

The pushed predicate mirrors `resolve_and_compare` exactly, including its
missing-key and empty-string guards. It is never the authority:
`apply_read_policy_to_data` still runs on every row that reaches the response.

**Filters:** `machine_name`, `current_state` (single state), `exclude_states`
(comma-separated, backs the hide-terminal toggle), `entity_type_name`,
`entity_type_id`, `assignee_ids` (comma-separated; the `__unassigned__` sentinel
matches rows with no assignee), `search` (matches the entity data blob),
`identifier`, `anchor_entity_id`, `include_archived`

`search` matches only the entity-data keys the caller's read policy leaves
visible and unmasked (plus the identifier, which the policy always exempts).
It is a SQL predicate, so it runs before the row is projected — an
unrestricted blob match would let a caller probe a hidden field's contents by
watching which rows come back. Roles with no field restriction at all
(`visible_fields is None`) still match the whole blob.

**Projection:** `fields` (comma-separated entity-data keys), `thumbnail_field`

**Sorting:** `sort_by` one of `identifier`, `display_name`, `state`, `created`,
`due_date`; `sort_dir` `asc`|`desc`. Custom schema-field sorting is not
supported yet.

**Opt-in extras** via `include` (comma-separated): `state_counts` (per-state
totals honouring every filter except `current_state` — powers kanban column
badges), `total_count` (exact match count for page numbering),
`identifier_options` (distinct identifiers, capped at 200)

`scan_truncated` is set when a row scan stopped at its cap rather than at the
data. Only the fallback path above can reach it. When true the response is a
prefix: counts understate and `has_more` may be `false` while more rows exist.

**Response:** `WorkflowEnrollmentSummaryPage`

---

## Transitions

### `GET /entities/{entity_id}/transitions/available`
Lists transitions available from the entity's current state. Frontend uses this to render action buttons before asking for execution.

**Path:** `entity_id`  
**Query params:** `machine_name`, `workflow_id`, `current_state`, `inputs_json` (optional JSON object)
**Response:** `AvailableTransitionsResponse`

---

### `GET /entities/{entity_id}/transitions/{trigger}/preflight`
Returns transition readiness without mutating state. Reports which required fields are missing and which guards block the move.

**Path:** `entity_id`, `trigger`  
**Query params:** `machine_name`, `workflow_id`, `current_state`, `inputs_json` (optional JSON object)
**Response:** `TransitionPreflightResponse`

---

### `POST /entities/{entity_id}/transitions`
Executes one workflow transition. Resolves the selected enrollment's workflow version, evaluates guards, applies the state change, records history, and emits task events. Supports idempotency via `idempotency_key`.

**Path:** `entity_id`  
**Body:** `TransitionExecuteRequest` (`workflow_id` selects the exact enrollment when an entity is enrolled more than once)
**Response:** `TransitionExecutionResponse`

---

### `GET /entities/{entity_id}/transitions/history`
Returns the transition audit trail for an entity including blocked reasons, executed tasks, and timing.

**Path:** `entity_id`  
**Response:** `TransitionHistoryResponse`

---

### `GET /entities/{entity_id}/events/history`
Returns the committed event log for an entity — transition events and task execution events.

**Path:** `entity_id`  
**Response:** `EventHistoryResponse`
