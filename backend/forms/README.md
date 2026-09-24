# Forms Module

Self-contained module for form schema management and public form submission on the Newtuple platform. The module owns entity type schemas (reusable field definitions bound to an entity type), picklists (dropdown option sets), and the public endpoints that let external users fill out and submit forms without authentication — driven by a signed JWT in the URL.

---

## Module Structure

```
forms/
├── controller.py       REST endpoints (FormsRestController)
├── manager.py          Business logic (FormsServiceManager)
├── db_models.py        ORM models + DB persistence (EntityTypeSchemaModel, PicklistModel, FormsModelService)
└── models/
    ├── interface.py    Shared contracts (EntityTypeSchemaContract, PicklistContract)
    ├── request.py      Inbound Pydantic schemas (EntityTypeSchemaCreateRequest, PicklistCreateRequest, etc.)
    └── response.py     Outbound Pydantic schemas (EntityTypeSchemaResponse, PicklistResponse, etc.)
```

---

## API Endpoints

All routes are mounted under `/v1/api`. Schema and picklist management endpoints require a valid JWT. Public form endpoints do not require authentication.

### Entity Type Schemas

| Method   | Path                              | Role Required | Description |
|----------|-----------------------------------|---------------|-------------|
| `POST`   | `/v1/api/forms/config`            | `ADMIN`       | Create a new entity type schema |
| `GET`    | `/v1/api/forms/config`            | `READ`        | List all schemas (filterable by `schema_key`, `entity_type`) |
| `GET`    | `/v1/api/forms/config/{schema_key}` | `READ`      | Get a single schema |
| `PUT`    | `/v1/api/forms/config/{schema_key}` | `ADMIN`     | Update a schema |
| `DELETE` | `/v1/api/forms/config/{schema_key}` | `ADMIN`     | Delete a schema |

**Create/update request body:**

```json
{
  "schema_key": "client__onboarding",
  "name": "Client Onboarding Form",
  "description": "Fields collected during client onboarding",
  "entity_type": "client",
  "fields": [
    { "field": "clientname", "type": "string", "required": true },
    { "field": "clientemail", "type": "email", "required": true }
  ],
  "is_active": true
}
```

Change detection is hash-based — updating a schema with identical content returns a `409 Conflict`.

---

### Picklists

| Method   | Path                                    | Role Required | Description |
|----------|-----------------------------------------|---------------|-------------|
| `POST`   | `/v1/api/config/picklists`              | `ADMIN`       | Create a picklist |
| `GET`    | `/v1/api/config/picklists`              | `READ`        | List all picklists |
| `GET`    | `/v1/api/config/picklists/{picklist_id}`| `READ`        | Get a single picklist |
| `PUT`    | `/v1/api/config/picklists/{picklist_id}`| `ADMIN`       | Update a picklist |
| `DELETE` | `/v1/api/config/picklists/{picklist_id}`| `ADMIN`       | Delete a picklist |

---

### Public Form Endpoints (no auth)

These endpoints are called by the frontend public form page and do not require a JWT.

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/v1/api/forms/public/{token}` | Load a form by signed token |
| `POST` | `/v1/api/forms/public/submit`  | Submit a form by signed token |
| `GET`  | `/v1/api/forms/public/entity/{entity_id}` | Load a form by entity ID |
| `POST` | `/v1/api/forms/public/entity/{entity_id}/submit` | Submit a form by entity ID |

**Token lookup priority:**

1. Token contains `run_id` → look up action run directly (works for any action kind)
2. Action run found but has no `form_id` in config → fall back to entity lookup
3. Entity lookup → find latest `form.receive_data` `pending_external` run for the entity

This handles both `mail.send_email` (sends form link in email, `form_id` in config) and `form.receive_data` (standalone wait action) in the same URL format.

**Submit request body:**

```json
{
  "token": "<signed-jwt>",
  "fields": {
    "clientname": "John Doe",
    "clientemail": "john@example.com"
  }
}
```

On successful submission:
- Fields are saved to the entity (or deferred to the action run if `defer_save: true`)
- The configured `outcome_triggers.received` workflow transition fires
- An `ACTION_FORM_SUBMITTED` event is emitted to the entity audit log

---

## Form Token Format

Form links are signed JWTs created at action execution time. The token payload contains:

```json
{
  "type": "form_link",
  "entity_id": "...",
  "run_id": "...",
  "org_id": "...",
  "exp": 1779384472
}
```

Tokens expire after 24 hours by default.

---

## `defer_save` Mode

When a workflow action sets `defer_save: true` in its config, submitted form fields are stored on the action run record (`resolved_config_json.submitted_fields`) instead of being written to the entity immediately. This is used when a downstream approval step needs to review the data before it is committed.

The `mail.send_approval` executor reads these deferred fields and displays them in the approval email. On approval, the background jobs module writes them to the entity via `save_deferred_fields_to_entity`.

---

## Database Schema

### `entity_type_schema` table (definitions schema)

| Column          | Type           | Nullable | Default   | Description |
|-----------------|----------------|----------|-----------|-------------|
| `id`            | `VARCHAR(36)`  | NOT NULL | `uuid4()` | Primary key |
| `organization_id`| `VARCHAR(36)` | NOT NULL | —         | Tenant scoping |
| `schema_key`    | `VARCHAR(128)` | NOT NULL | —         | Unique identifier within the org (e.g. `client__onboarding`) |
| `name`          | `VARCHAR(128)` | NOT NULL | —         | Human-readable name |
| `description`   | `TEXT`         | NULL     | —         | Optional description |
| `entity_type`   | `VARCHAR(128)` | NOT NULL | —         | Entity type this schema belongs to |
| `fields_json`   | `JSONB`        | NOT NULL | `[]`      | Array of field definition objects |
| `is_active`     | `BOOLEAN`      | NOT NULL | `true`    | Whether this schema is available for use |
| `content_hash`  | `VARCHAR(64)`  | NULL     | —         | SHA-256 of entity_type + fields for change detection |
| `created_at`    | `TIMESTAMPTZ`  | NOT NULL | `now()`   | Creation timestamp |
| `updated_at`    | `TIMESTAMPTZ`  | NOT NULL | `now()`   | Last update timestamp |

### Indexes

| Index name | Columns | Purpose |
|------------|---------|---------|
| `ix_entity_type_schema_lookup` | `(organization_id, schema_key, is_active)` | Primary lookup pattern |
| `ix_entity_type_schema_entity_type` | `(entity_type)` | Filter by entity type |
| `ix_entity_type_schema_content_hash` | `(content_hash)` | Change detection |

### `picklists` table

| Column          | Type           | Nullable | Default   | Description |
|-----------------|----------------|----------|-----------|-------------|
| `pk`            | `VARCHAR(36)`  | NOT NULL | `uuid4()` | Internal primary key |
| `id`            | `VARCHAR(128)` | NOT NULL | —         | User-defined identifier |
| `organization_id`| `VARCHAR(36)` | NOT NULL | —         | Tenant scoping |
| `name`          | `VARCHAR(256)` | NOT NULL | —         | Display name |
| `options`       | `JSONB`        | NOT NULL | `[]`      | Array of `{label, value}` option objects |
| `created_at`    | `TIMESTAMPTZ`  | NOT NULL | `now()`   | Creation timestamp |
| `updated_at`    | `TIMESTAMPTZ`  | NOT NULL | `now()`   | Last update timestamp |

---

## Field Definition Object

Each entry in `fields_json` follows this shape:

```json
{
  "field": "clientname",
  "type": "string",
  "required": false,
  "nullable": true,
  "default": null,
  "enum_values": [],
  "picklist_id": null,
  "description": "Client full name"
}
```

Supported `type` values: `string`, `email`, `number`, `boolean`, `date`, `select`, `multi_select`, `file`.
