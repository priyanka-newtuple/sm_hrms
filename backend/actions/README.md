# Actions Module

Self-contained module for managing action definitions and querying action run history on the Newtuple platform. Action definitions form the catalog of reusable workflow actions (e.g. `mail.send_email`, `form.receive_data`). Action runs are the per-entity execution records produced by the background jobs engine when the workflow triggers an action.

---

## Module Structure

```
actions/
├── controller.py       REST endpoints (ActionsRestController)
├── manager.py          Business logic (ActionsServiceManager)
└── db_models.py        ORM model + DB persistence service (ActionDefinitionModel, ActionsModelService)
```

---

## API Endpoints

All routes are mounted under `/v1/api` and require a valid JWT (Bearer token). The actor's `organization_id` and `roles` are read from the token and used for authorization.

### 1. List Action Definitions

```
GET /v1/api/action-definitions
```

Returns the full catalog of action definitions registered in the organization.

**Response** `200 OK`

```json
{
  "items": [
    {
      "kind": "mail.send_email",
      "name": "Send Email",
      "description": "Send an email using a template.",
      "input_schema": {},
      "output_schema": {}
    }
  ],
  "total": 1
}
```

---

### 2. Get Action Definition by Kind

```
GET /v1/api/action-definitions/{kind}
```

Returns a single action definition by its kind identifier.

**Path parameters**

| Parameter | Type   | Description                              |
|-----------|--------|------------------------------------------|
| `kind`    | string | Action kind (e.g. `mail.send_email`)     |

**Error responses**

| Status | Reason |
|--------|--------|
| `404`  | Action definition not found |

---

### 3. List Action Runs for an Entity

```
GET /v1/api/action-runs/{entity_id}
```

Returns the history of all action runs executed for a given entity, ordered by creation time descending.

**Path parameters**

| Parameter   | Type   | Description              |
|-------------|--------|--------------------------|
| `entity_id` | string | UUID of the entity       |

**Required role:** `READ`

**Response** `200 OK`

```json
{
  "items": [
    {
      "run_id": "...",
      "entity_id": "...",
      "action_kind": "mail.send_email",
      "status": "succeeded",
      "outcome": "sent",
      "attempts": 1,
      "created_at": "2026-05-17T10:00:00+00:00",
      "completed_at": "2026-05-17T10:00:01+00:00"
    }
  ],
  "total": 1
}
```

**Error responses**

| Status | Reason |
|--------|--------|
| `401`  | Missing or invalid JWT |
| `403`  | Actor does not have READ role |

---

## Database Schema

### `action_definitions` table

| Column          | Type           | Nullable | Default    | Description                              |
|-----------------|----------------|----------|------------|------------------------------------------|
| `definition_id` | `VARCHAR(36)`  | NOT NULL | `uuid4()`  | Primary key                              |
| `organization_id`| `VARCHAR(36)` | NOT NULL | —          | Tenant scoping                           |
| `kind`          | `VARCHAR(128)` | NOT NULL | —          | Unique action identifier (e.g. `mail.send_email`) |
| `name`          | `VARCHAR(256)` | NOT NULL | —          | Human-readable name                      |
| `description`   | `TEXT`         | NULL     | —          | Optional description                     |
| `input_schema`  | `JSONB`        | NOT NULL | `{}`       | JSON Schema for input fields             |
| `output_schema` | `JSONB`        | NOT NULL | `{}`       | JSON Schema for output/outcome fields    |
| `created_at`    | `TIMESTAMPTZ`  | NOT NULL | `now()`    | Insertion timestamp                      |

### `action_runs` table

| Column                | Type           | Nullable | Default    | Description                                              |
|-----------------------|----------------|----------|------------|----------------------------------------------------------|
| `run_id`              | `VARCHAR(36)`  | NOT NULL | —          | Primary key                                              |
| `organization_id`     | `VARCHAR(36)`  | NOT NULL | —          | Tenant scoping                                           |
| `entity_id`           | `VARCHAR(36)`  | NOT NULL | —          | Entity this run was triggered for                        |
| `action_kind`         | `VARCHAR(128)` | NOT NULL | —          | The executor kind that was invoked                       |
| `config_json`         | `JSONB`        | NOT NULL | —          | Raw config from the workflow state definition            |
| `resolved_config_json`| `JSONB`        | NULL     | —          | Config after `$entity.*` placeholder resolution          |
| `status`              | `VARCHAR(32)`  | NOT NULL | —          | `pending` / `running` / `succeeded` / `failed` / `pending_external` |
| `outcome`             | `VARCHAR(64)`  | NULL     | —          | Executor outcome string (e.g. `sent`, `approved`)        |
| `attempts`            | `INTEGER`      | NOT NULL | `0`        | Number of execution attempts made                        |
| `scheduled_at`        | `TIMESTAMPTZ`  | NULL     | —          | When the run is next eligible for execution (for retries)|
| `external_timeout_at` | `TIMESTAMPTZ`  | NULL     | —          | Deadline for external waits (form / approval)            |
| `created_at`          | `TIMESTAMPTZ`  | NOT NULL | `now()`    | Insertion timestamp                                      |
| `updated_at`          | `TIMESTAMPTZ`  | NOT NULL | `now()`    | Last modification timestamp                              |
| `completed_at`        | `TIMESTAMPTZ`  | NULL     | —          | When the run reached a terminal state                    |

---

## Action Run Lifecycle

```
pending → running → succeeded
                 ↘ failed
                 ↘ pending_external → succeeded (on external callback)
                                   ↘ failed    (on timeout)
```

Action runs are created by the background jobs engine when a workflow state's `on_state_action` is triggered. The actions module provides read-only access to this history.
