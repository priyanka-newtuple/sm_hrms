# Repository Map: `newtuple/state-machine`

Last updated: 2026-05-29

## Purpose

`state-machine` is a generic workflow/state-machine runtime intended to power multiple cockpit-style products. The current product direction is ATS first, then PMO and other cockpit domains. The repository is organized around a reusable platform core plus domain/application layers.

At a high level:

- Backend: FastAPI, SQLAlchemy, Pydantic, PostgreSQL
- Frontend: React, TypeScript, Vite, Tailwind
- Database: PostgreSQL via Docker for local development
- Workflow model: versioned state-machine definitions with runtime entity state, guards, transitions, tasks, validation, dry-runs, and audit trails

## Top-level layout

```text
state-machine/
├── backend/                  # FastAPI backend and platform modules
├── frontend/                 # React/Vite frontend
├── design_docs/              # Architecture and design notes
├── docker-compose.local.yml  # Local DB/backend/frontend composition
├── docker-compose.prod.yml   # Production composition
├── Makefile                  # Developer commands
└── README.md                 # Setup, env, structure, and operational notes
```

## Backend map

```text
backend/
├── main.py                   # FastAPI app entrypoint and module wiring
├── workflow/                 # Core state-machine/workflow runtime
├── entities/                 # Runtime entity registry, records, states, events
├── forms/                    # Form definitions/config used by workflow/entity flows
├── actions/                  # Action definitions and execution hooks
├── background_jobs/          # Background job orchestration
├── executor/                 # Execution service used by jobs/actions
├── agent/                    # AI agent definitions and sessions
├── auth/                     # Local auth and SSO
├── roles/                    # Role/RBAC module
├── user/                     # User module
├── organizations/            # Organization/multi-tenant management
├── tenants/                  # Tenant management
├── integrations/             # External integration management
├── llm/                      # LLM service layer
├── filehandler/              # File storage/handling
├── fileprocessor/            # File processing and LLM-assisted extraction
├── communications/           # Communication abstractions
├── notifications/            # Notification dispatch
├── mail/                     # SMTP/inbound/outbound mail support
├── tasks/                    # Task management
├── comments/                 # Comments on domain records
├── views/                    # View configuration/querying
├── projections/              # Projection/read-model support
├── dashboard/                # Dashboard APIs
├── health/                   # Health/status endpoints
├── bootstrap/                # Startup bootstrap, migrations, seed data
├── database/                 # Shared DB manager/Base/session wiring
├── common/                   # Shared config, auth helpers, logger, utilities
├── alembic/                  # Migrations
├── etc/                      # .env template/config files
└── requirements.txt          # Backend runtime dependencies
```

### Backend app composition

`backend/main.py` is the composition root. It creates model services, service managers, and REST controllers for all modules, wires shared dependencies, and mounts controllers into a common FastAPI router.

Important state-machine wiring in `main.py`:

- `FormsModelService` is created before entities/workflow because workflow uses form metadata in some flows.
- `EntitiesModelService` and `EntitiesServiceManager` provide canonical runtime entity storage.
- `WorkflowModelService` and `WorkflowServiceManager` provide definition persistence and state-machine orchestration.
- `WorkflowServiceManager` receives `entities_service_manager` and `forms_db_model_service` so workflow operations can validate definitions and write runtime state through the newer entity model.
- `BackgroundJobsServiceManager` and `FormsServiceManager` are back-linked to `workflow_service_manager` after workflow is constructed.

## Core workflow/state-machine module

```text
backend/workflow/
├── controller.py             # REST API routes under /workflow-state-machines
├── manager.py                # Main orchestration and business logic
├── db_models.py              # SQLAlchemy models + persistence adapter
└── models/
    ├── interface.py          # Pydantic contracts and in-memory records
    ├── request.py            # Request DTO exports/aliases
    ├── response.py           # Response DTO exports/aliases
    └── __init__.py           # Public model exports
```

### `workflow/manager.py`

This is the most important file for state-machine behavior.

Responsibilities:

- Build the default/reference workflow template.
- Create and seed workflow drafts.
- Save draft definitions with structural validation.
- Validate candidate workflow definitions.
- Run dry-run and compatibility checks before publishing.
- Publish versioned workflow definitions.
- List workflow paths.
- List available transitions for an entity.
- Perform transition preflight checks.
- Execute transitions against runtime entities.
- Record transition history and event history.
- Compare workflow versions.

Key concepts:

- A state machine is a versioned workflow definition.
- Version `0` is treated as a draft row.
- Published versions are `>= 1`.
- Only one active published version exists per workflow family.
- Runtime mutable state is owned by the entities module, not by legacy workflow-local state rows.

### `workflow/controller.py`

This exposes the workflow runtime through REST endpoints. The route group is tagged as `state-machines`, with most paths rooted at `/workflow-state-machines`.

Important route families:

- Status/template
  - `GET /workflow-state-machines/status`
  - `GET /workflow-state-machines/default-template`
- Definition lifecycle
  - `POST /workflow-state-machines/draft`
  - `PUT /workflow-state-machines/{row_id}/draft`
  - `POST /workflow-state-machines/{row_id}/publish`
  - `GET /workflow-state-machines`
  - `GET /workflow-state-machines/{row_id}`
- Validation and analysis
  - `POST /workflow-state-machines/validate`
  - `POST /workflow-state-machines/workflow-paths`
- Runtime/entity operations
  - endpoints for enrollment, transition preflight, transition execution, history, and available transitions are also implemented in this controller.

The controller is intentionally thin: it resolves the actor, delegates to `WorkflowServiceManager`, and maps domain exceptions to HTTP status codes.

### `workflow/db_models.py`

This is the persistence adapter for workflow definitions and reports.

Primary tables:

- `workflow_state_machines`
  - Stores draft and published definitions.
  - Includes `organization_id`, `machine_key`, `machine_name`, `entity_type`, `version`, `is_active`, `archived_at`, `definition_json`, and optional `canvas_metadata_json`.
  - Enforces uniqueness across organization, machine, and version for non-archived rows.
- `workflow_definition_reports`
  - Stores validation, compatibility, and dry-run reports.
  - Tracks report type, machine/version context, issue JSON, checked entities, and compatibility counts.

`WorkflowModelService` supports both database-backed operation and in-memory mode for tests.

### `workflow/models/interface.py`

This defines the typed contract for the state-machine domain.

Important model groups:

- Definition schema
  - `StateMachineDefinition`
  - `EntitySchema`
  - `EntityField`
  - `State`
  - `Transition`
  - `RequiredField`
  - `Guard`
  - `TransitionTask`
  - `StateAction`
- Enums/constants
  - `GuardType`
  - `EntityFieldType`
  - `StateTag`
  - `TaskName`
  - `TransitionStatus`
  - `ReportType`
  - `ActivityType`
- Records/responses
  - state-machine records
  - draft records
  - validation/dry-run reports
  - transition execution/history records

Validation rules live close to the models through Pydantic validators. This includes checks for non-empty names, unique states/fields, supported entity field types, valid state tags, supported guard types, and internal coherence between `entity_type` and `entity_schema.entity_type`.

## Runtime entity module

```text
backend/entities/
├── controller.py             # Entity metadata/runtime APIs
├── manager.py                # Entity business logic and auth-aware wrappers
├── db_models.py              # Entity SQLAlchemy tables + persistence service
└── models/                   # Entity request/response/interface contracts
```

The workflow module depends on `entities` for runtime state. The design intent is:

- `workflow` owns versioned definitions and transition rules.
- `entities` owns entity types, entity records, entity state, entity events, relations, and transition attempts.
- Workflow execution should write through `EntitiesServiceManager` so runtime state and audit history stay canonical.

When debugging state transitions, inspect both modules together:

1. `backend/workflow/manager.py` for decision-making and transition orchestration.
2. `backend/entities/manager.py` for runtime entity/state/event APIs.
3. `backend/entities/db_models.py` for actual runtime table persistence.

## Frontend map

```text
frontend/
└── src/
    ├── App.tsx                       # Top-level routes and providers
    ├── pages/
    │   ├── funnel/                   # Workflow builder/editor UI
    │   ├── records/                  # Runtime entity records UI
    │   ├── Pipeline.tsx              # Pipeline visualization/detail page
    │   ├── settings/                 # Admin/settings area
    │   └── DashboardPage.tsx         # Dashboard route
    ├── lib/
    │   └── state-machine/            # Frontend state-machine document helpers/validation
    ├── core/
    │   ├── services/api              # API client layer
    │   ├── auth                      # Auth provider and protected routes
    │   ├── contexts                  # Org selector context
    │   └── agent                     # Agent provider/context
    ├── components/                   # Shared UI components
    └── layouts/                      # App shell/layouts
```

### Frontend state-machine UI

The main workflow editor route is `frontend/src/pages/funnel/index.tsx`.

Key routes from `App.tsx`:

- `/funnel/create`
- `/funnel/create/wizard`
- `/funnel/:stateMachineId/edit`
- `/pipeline/:id`
- `/records`
- `/records/:entityType`

The funnel editor supports at least two editing modes:

- `wizard`
- `canvas`

It uses:

- `useStateMachineDoc` for loading, creating, saving drafts, publishing, and maintaining editor document state.
- `validateMachine` for client-side validation.
- `api.stateMachines` for backend calls such as create draft, validate, save draft, and publish.

## Main state-machine lifecycle

### 1. Create a draft

Frontend calls the draft endpoint. Backend creates a version `0` row in `workflow_state_machines` with a generated `machine_name` and minimal initial definition.

Main files:

- `frontend/src/pages/funnel/index.tsx`
- `frontend/src/lib/state-machine/useStateMachineDoc.*`
- `backend/workflow/controller.py`
- `backend/workflow/manager.py`
- `backend/workflow/db_models.py`

### 2. Edit and save draft

Frontend maintains a workflow document and saves the full definition plus optional canvas metadata. Backend parses the definition and returns validation issues, but still persists invalid drafts so users can continue editing.

Main files:

- `frontend/src/pages/funnel/index.tsx`
- `frontend/src/pages/funnel/canvas/WorkflowEditor.*`
- `frontend/src/pages/funnel/wizard.*`
- `backend/workflow/manager.py`

### 3. Validate candidate definition

Backend validates structure, checks state/transition coherence, and may run dry-run/compatibility checks. Reports are persisted in `workflow_definition_reports`.

Main files:

- `backend/workflow/manager.py`
- `backend/workflow/db_models.py`
- `backend/workflow/models/interface.py`

### 4. Publish workflow

Backend validates the candidate, computes the next version, writes a published row, and deactivates other active rows in the same workflow family when the new version is active.

Main files:

- `backend/workflow/manager.py`
- `backend/workflow/db_models.py`

### 5. Enroll/create runtime entities

Published definitions describe the entity schema and allowed state transitions. Runtime instances and their mutable states are stored by the `entities` module.

Main files:

- `backend/workflow/manager.py`
- `backend/entities/manager.py`
- `backend/entities/db_models.py`

### 6. Execute transitions

Transition execution generally follows this shape:

1. Resolve actor and organization.
2. Load the active/published workflow definition.
3. Load runtime entity and current state.
4. Check transition availability from current state.
5. Validate required fields.
6. Evaluate guards.
7. Run pre-transition tasks if configured.
8. Commit new state through the entities module.
9. Record transition attempts/events/activity history.
10. Run post-transition tasks if configured.

Main files:

- `backend/workflow/manager.py`
- `backend/entities/manager.py`
- `backend/actions/`
- `backend/background_jobs/`
- `backend/executor/`
- `backend/notifications/`
- `backend/mail/`

## Common debugging paths

### API route not responding

Start with:

1. `backend/main.py` to confirm controller wiring.
2. `backend/workflow/controller.py` to confirm route path/method.
3. Auth dependencies in `backend/common/auth.py` and `backend/auth/`.

### Definition fails validation

Start with:

1. `backend/workflow/models/interface.py` for schema/model validators.
2. `backend/workflow/manager.py` for cross-field and graph-level validation.
3. `workflow_definition_reports` table for persisted issue output.

### Draft saves but publish fails

Start with:

1. `backend/workflow/manager.py` publish flow.
2. Validation and dry-run report generation.
3. `workflow_state_machines` for draft row/version conflicts.
4. `workflow_definition_reports` for the latest candidate issues.

### Transition is blocked

Start with:

1. Available transition calculation in `backend/workflow/manager.py`.
2. Required field and guard evaluation in `backend/workflow/manager.py`.
3. Entity state and transition attempts in `backend/entities/db_models.py`.
4. Domain data stored in entity records.

### Frontend editor looks wrong

Start with:

1. `frontend/src/pages/funnel/index.tsx` for view switching and save/validate/publish actions.
2. `frontend/src/lib/state-machine/useStateMachineDoc.*` for load/save document state.
3. `frontend/src/lib/state-machine/validate.*` for client-side validation.
4. `frontend/src/pages/funnel/canvas/` for visual editor behavior.
5. `frontend/src/pages/funnel/wizard.*` for wizard behavior.

## Extension guide

### Add a new field type

Likely touch points:

- `backend/workflow/models/interface.py`
  - Add enum value to `EntityFieldType`.
  - Update `ENTITY_FIELD_TYPE_ALL` if needed.
  - Update `_matches_entity_field_type`.
- Frontend state-machine validation and editor controls.
- Any form rendering or schema-to-form conversion code.

### Add a new guard type

Likely touch points:

- `backend/workflow/models/interface.py`
  - Add enum value to `GuardType`.
  - Update `GUARD_TYPE_ALL` / aliases if required.
- `backend/workflow/manager.py`
  - Add evaluation logic.
  - Add validation and dry-run behavior.
- Frontend builder controls for guard configuration.

### Add a new transition task

Likely touch points:

- `backend/workflow/models/interface.py`
  - Add task identity if it is a built-in task.
- `backend/workflow/manager.py`
  - Add execution hook/dispatch.
- `backend/actions/`, `backend/background_jobs/`, or `backend/executor/` if the task runs asynchronously or integrates with external actions.
- Frontend task configuration UI.

### Add a new cockpit/domain pack

Expected approach:

1. Define domain entity schema.
2. Define workflow states, transitions, guards, tasks, and SLAs.
3. Seed/publish a workflow definition for that domain.
4. Add frontend pages or adapt existing `records`, `pipeline`, and `funnel` views.
5. Add integrations/actions only where domain-specific behavior is needed.

Keep domain-specific behavior outside the core workflow engine unless it is reusable across cockpits.

## Files to read first

For backend/state-machine work:

1. `backend/main.py`
2. `backend/workflow/manager.py`
3. `backend/workflow/controller.py`
4. `backend/workflow/db_models.py`
5. `backend/workflow/models/interface.py`
6. `backend/entities/manager.py`
7. `backend/entities/db_models.py`

For frontend/editor work:

1. `frontend/src/App.tsx`
2. `frontend/src/pages/funnel/index.tsx`
3. `frontend/src/lib/state-machine/useStateMachineDoc.*`
4. `frontend/src/lib/state-machine/validate.*`
5. `frontend/src/pages/funnel/canvas/WorkflowEditor.*`
6. `frontend/src/pages/records/`
7. `frontend/src/pages/Pipeline.tsx`

## Notes and caveats

- This map is based on the current visible repository structure and key entry-point files.
- The exact frontend helper filenames under `frontend/src/lib/state-machine/` and some editor subcomponents should be verified when working locally, because the GitHub connector view used to create this map did not expose a full recursive tree listing.
- Keep this file updated when major module boundaries or route names change.
