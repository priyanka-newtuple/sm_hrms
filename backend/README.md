# Modular Backend

This directory contains the **generic-first backend runtime** for building multiple product skins on a shared foundation.

The design goal is:
- keep core capabilities reusable across domains,
- keep API contracts explicit and typed,
- keep module boundaries clear (`controller -> manager -> db_models`),
- keep legacy route aliases where required for compatibility.

---

## 1) High-Level Architecture

The runtime is organized around modules that all follow the same structure:

- `controller.py`
  - owns FastAPI route definitions only,
  - reads typed request models,
  - calls manager methods,
  - translates known exceptions to HTTP responses with explicit `except` blocks.

- `manager.py`
  - owns business orchestration,
  - validates business-level behavior,
  - coordinates module dependencies,
  - converts persistence output into response contracts.

- `db_models.py`
  - owns persistence adapter logic,
  - currently in-memory style services in modular backend,
  - raises persistence-level exceptions for storage operations.

- `models/`
  - `request.py`: API request contracts,
  - `response.py`: API response contracts,
  - `interface.py`: shared interfaces/contracts used across layers.

This is the same controller-manager-db_models separation pattern as your project reference.

---

## 2) Request Lifecycle (Per API)

For every API call in modular backend:

1. Controller receives request and parses typed request model.
2. Controller calls manager method.
3. Manager applies orchestration and permission/business checks.
4. Manager calls db_models service for persistence reads/writes.
5. Manager returns typed response model.
6. Controller maps exceptions to HTTP responses with explicit readable `except` blocks.

---

## 3) Runtime Entry and Wiring

Main entrypoint: `backend/modular_backend/main.py`

What `main.py` does:

1. Loads environment (`-e/--env`).
2. Builds shared configuration (`common/configuration.py`).
3. Builds database manager (`database/manager.py`).
4. Instantiates each module's db service, manager, and controller.
5. Registers routes via `controller.prepare(app_router)`.
6. Adds middleware (gzip, CORS, request-id, timeout).
7. Mounts routes based on feature flags.

### Route Mounting Modes

By default:
- original app routes are mounted,
- generic modular routes are not mounted unless enabled.

Flags used in `main.py`:
- `MODULAR_INCLUDE_ORIGINAL_APP_ROUTES` (default `true`)
- `MODULAR_INCLUDE_ORIGINAL_V1_PREFIX` (default `false`)
- `MODULAR_ENABLE_GENERIC_ROUTES` (default `false`)

---

## 4) Directory Layout

```text
backend/modular_backend/
  main.py
  common/
  database/
  exceptions/

  agents/
  annotations/
  auth/
  background_jobs/
  communications/
  documents/
  entities/
  forms/
  health/
  integrations/
  llm/
  playbooks/
  tenants/
  transcription/
  views/

  docs/
  tests/
```

---

## 5) Module Dependency Flow

Cross-module dependencies are intentionally explicit in manager wiring:

- `auth` is used by permission-aware modules.
- `communications` is base capability for notifications/comments.
- `annotations` is a facade over communications comments.
- `entities` is metadata/lifecycle capability.
- `forms` is a facade over entities form metadata.
- `views` depends on auth for projection access checks.
- `integrations`, `documents`, `transcription` use auth-scoped behavior.

This keeps modules reusable while allowing composition.

---

## 6) Module-Wise Details

## `auth`

Purpose:
- identity and access checks,
- role grants,
- token introspection.

API routes:
- `GET /auth/status`
- `GET /identity_access/status` (legacy alias)
- `POST /auth/check`
- `POST /identity_access/check` (legacy alias)
- `POST /auth/roles/grant`
- `POST /identity_access/roles/grant` (legacy alias)
- `POST /auth/token/introspect`
- `POST /identity_access/token/introspect` (legacy alias)

Layer roles:
- Controller: auth route definitions + explicit HTTP error mapping.
- Manager: permission matrix evaluation and actor org scoping.
- DB models: in-memory role and token registry.
- Models: typed request/response/interface contracts.

---

## `tenants`

Purpose:
- generic tenant/organization capability shell.

API routes:
- `GET /tenants/status`
- `GET /organizations/status` (legacy alias)

Layer roles:
- Controller: status endpoints.
- Manager: tenant capability facade.
- DB models: adapter shell for tenant state.

---

## `agents`

Purpose:
- generic agent runtime capability shell.

API routes:
- `GET /agents/status`
- `GET /agent_ai/status` (legacy alias)

Layer roles:
- Controller: status endpoints.
- Manager: agent capability facade.
- DB models: adapter shell for agent persistence needs.

---

## `llm`

Purpose:
- generic LLM capability module.

API routes:
- `GET /llm/status`

Layer roles:
- Controller: status endpoint.
- Manager: LLM capability manager shell.
- DB models: adapter shell.

---

## `integrations`

Purpose:
- external integration and scheduling capability.

API routes:
- `GET /integrations/status`
- `GET /integrations_calendar/status` (legacy alias)
- `POST /integrations/connect`
- `POST /integrations_calendar/connect` (legacy alias)
- `GET /integrations/accounts/{organization_id}`
- `GET /integrations_calendar/accounts/{organization_id}` (legacy alias)
- `POST /integrations/events/schedule`
- `POST /integrations_calendar/events/schedule` (legacy alias)
- `GET /integrations/events`
- `GET /integrations_calendar/events` (legacy alias)

Layer roles:
- Controller: integration + calendar route APIs.
- Manager: integration account checks and event orchestration.
- DB models: integration account and event persistence adapters.

---

## `communications`

Purpose:
- notifications and email-config capability.

API routes:
- `GET /communications/status`
- `GET /collaboration/status` (legacy alias)
- `POST /communications/notifications`
- `POST /collaboration/notifications` (legacy alias)
- `PUT /communications/email-config`
- `PUT /collaboration/email-config` (legacy alias)
- `GET /communications/email-config/{organization_id}`
- `GET /collaboration/email-config/{organization_id}` (legacy alias)

Layer roles:
- Controller: communication APIs with actor-role dependencies.
- Manager: notification creation, email-config orchestration.
- DB models: comments/notifications/email config persistence primitives.

---

## `annotations`

Purpose:
- comments/annotation facade using communications module.

API routes:
- `GET /annotations/status`
- `POST /annotations/comments`
- `POST /collaboration/comments` (legacy alias)
- `GET /annotations/comments/{organization_id}/{entity_id}`
- `GET /collaboration/comments/{organization_id}/{entity_id}` (legacy alias)

Layer roles:
- Controller: annotation endpoints.
- Manager: delegates to communications manager for comment flows.
- DB models: compatibility adapter shell.

---

## `entities`

Purpose:
- generic metadata registry and lifecycle resolution.

API routes:
- `GET /entities/status`
- `GET /metadata_registry/status` (legacy alias)
- `POST /entities/entity-types`
- `POST /metadata_registry/entity-types` (legacy alias)
- `GET /entities/entity-types/{organization_id}`
- `GET /metadata_registry/entity-types/{organization_id}` (legacy alias)
- `POST /entities/lifecycle/resolve`
- `POST /metadata_registry/lifecycle/resolve` (legacy alias)
- `POST /metadata_registry/funnel/resolve` (legacy alias)

Layer roles:
- Controller: entity metadata/lifecycle APIs.
- Manager: entity type, form, lifecycle orchestration.
- DB models: entity type and form config persistence contracts.
- Models: includes dual-term lifecycle/funnel compatibility.

---

## `forms`

Purpose:
- generic form config facade over entities metadata.

API routes:
- `GET /forms/status`
- `POST /forms/configs`
- `POST /metadata_registry/form-configs` (legacy alias)
- `GET /forms/configs/{organization_id}/{form_key}`
- `GET /metadata_registry/form-configs/{organization_id}/{form_key}` (legacy alias)

Layer roles:
- Controller: form config APIs.
- Manager: delegates to entities manager.
- DB models: adapter shell.

---

## `views`

Purpose:
- lifecycle projections, usage summaries, and heatmap refresh.

API routes:
- `GET /views/status`
- `GET /projections/status` (legacy alias)
- `POST /views/lifecycle-projections`
- `POST /projections/lifecycle-projections` (canonical compat)
- `POST /projections/pipeline` (legacy alias)
- `POST /views/lifecycle-projections/list`
- `POST /projections/lifecycle-projections/list` (canonical compat)
- `POST /projections/pipeline/list` (legacy alias)
- `GET /views/lifecycle-projections/{organization_id}/{subject_entity_id}`
- `GET /projections/lifecycle-projections/{organization_id}/{subject_entity_id}` (canonical compat)
- `GET /projections/pipeline/{organization_id}/{application_id}` (legacy alias)
- `POST /views/lifecycle-usage`
- `POST /projections/lifecycle-usage` (canonical compat)
- `POST /projections/pipeline-funnels` (legacy alias)
- `POST /views/lifecycle-heatmap/refresh`
- `POST /projections/lifecycle-heatmap/refresh` (canonical compat)
- `POST /projections/heatmap/refresh` (legacy alias)

Layer roles:
- Controller: projection APIs and compatibility routes.
- Manager: upsert/list/get projection orchestration and usage/heatmap calculations.
- DB models: projection rows and aggregated heatmap persistence/queries.
- Models: canonical + legacy alias fields (`subject_entity_id/application_id`, etc.).

---

## `documents`

Purpose:
- document ingest, status lifecycle, retrieval, extraction summary.

API routes:
- `GET /documents/status`
- `POST /documents/upload`
- `POST /documents/update-status`
- `POST /documents/list`
- `GET /documents/{organization_id}/{document_id}`
- `GET /documents/{organization_id}/{document_id}/extraction-summary`

Layer roles:
- Controller: document APIs.
- Manager: validation and lifecycle orchestration.
- DB models: document record persistence.

---

## `background_jobs`

Purpose:
- generic intake orchestration jobs and source uploads.

API routes:
- `GET /background_jobs/status`
- `GET /intake_orchestration/status` (legacy alias)
- `POST /background_jobs/intake-jobs`
- `POST /intake/jobs` (canonical generic)
- `POST /background_jobs/intake-sources/upload`
- `POST /intake/sources/upload` (canonical generic)
- `GET /background_jobs/intake-jobs/{organization_id}/{job_id}`
- `GET /intake/jobs/{organization_id}/{job_id}` (canonical generic)
- `GET /background_jobs/intake-jobs/{organization_id}`
- `GET /intake/jobs/{organization_id}` (canonical generic)

Layer roles:
- Controller: intake job APIs and aliases.
- Manager: intake orchestration logic.
- DB models: intake job and source persistence.

---

## `playbooks`

Purpose:
- generic playbook runtime capability facade.

API routes:
- `GET /playbooks/status`
- `GET /playbooks_runtime/status` (legacy alias)

Layer roles:
- Controller: status endpoints.
- Manager: playbooks capability facade.
- DB models: adapter shell.

---

## `transcription`

Purpose:
- transcription capability module (currently status-oriented shell).

API routes:
- `GET /transcription/status`

Layer roles:
- Controller: status endpoint.
- Manager: transcription capability shell.
- DB models: adapter shell.

---

## `health`

Purpose:
- liveness health endpoint.

API routes:
- `GET /health`

Layer roles:
- Controller: health route.
- Manager: simple health payload provider.

---

## 7) Cross-Cutting Shared Packages

- `common/`
  - configuration, logger/tracer, auth dependency helpers, enums, compatibility helpers, legacy app route bridge.

- `database/`
  - base DB service manager and engine/session helpers used by modules.

- `exceptions/`
  - shared domain/service/persistence exception taxonomy used by manager and db layers.

---

## 8) Contract and Compatibility Notes

1. All active modules are expected to use typed request/response models.
2. Compatibility routes are intentionally preserved where migration is ongoing.
3. Canonical generic naming is preferred for all new APIs.
4. Legacy aliases remain available to avoid breaking existing clients.

---

## 9) How to Add a New Module (Pattern)

1. Create `<module>/controller.py` with class-based `prepare(app_router, security)`.
2. Create `<module>/manager.py` for business orchestration.
3. Create `<module>/db_models.py` for persistence adapter logic.
4. Create `<module>/models/request.py`, `response.py`, `interface.py`.
5. Wire db -> manager -> controller in `_setup_generic_modules()` in `main.py`.
6. Keep controller exceptions explicit and readable in each API method.

This keeps new skins and capabilities predictable, reusable, and easy to extend.
