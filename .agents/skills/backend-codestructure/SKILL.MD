---
name: backend-codestructure
description: Enforces modular backend architecture patterns (controller/manager/db_models layering, naming conventions, wiring, and testing) when working on backend/modular_backend/ files.
allowed-tools: Read, Grep, Glob, Bash
model: sonnet4.6
---

# Backend Code Structure Skill

## Trigger

Auto-invoke this skill when creating or modifying files under `backend/modular_backend/`.

## Architecture Overview

The modular backend is a generic-first runtime organized around self-contained modules. Each module follows a strict **controller -> manager -> db_models** layering pattern with typed Pydantic contracts.

Reference: `backend/modular_backend/README.md`

## Module Anatomy

Every module lives in its own directory under `backend/modular_backend/<module>/` and contains:

```
<module>/
  __init__.py
  controller.py       # FastAPI route definitions (class-based)
  manager.py           # Business orchestration and validation
  db_models.py         # Persistence adapter (SQLAlchemy + in-memory fallback)
  models/
    __init__.py
    request.py         # API request contracts (Pydantic)
    response.py        # API response contracts (Pydantic)
    interface.py       # Cross-module contracts, enums, Protocols
```

Exception: `health/` has no `db_models.py` (listed in `OPTIONAL_DB_MODEL_MODULES`).

Reference implementation: `backend/modular_backend/tasks/` (full CRUD module)

## Naming Conventions

| Component | Class Name Pattern | Example |
|---|---|---|
| Controller | `<Module>RestController` | `TasksRestController` |
| Manager | `<Module>ServiceManager` | `TasksServiceManager` |
| DB service | `<Module>ModelService` | `TasksModelService` |
| SQLAlchemy model | `<Module>Model` (singular) | `TaskModel` |
| In-memory record | `<Module>Record` (singular) | `TaskRecord` |
| Interface contract | `<Module>Contract` (singular) | `TaskContract` |
| Read response | `<Module>ReadResponse` | `TaskReadResponse` |
| List response | `<Module>ListResponse` | `TaskListResponse` |
| Status response | `<Module>StatusResponse` | `TasksStatusResponse` |
| Create request | `<Module>CreateRequest` | `TaskCreateRequest` |
| Update request | `<Module>UpdateRequest` | `TaskUpdateRequest` |
| List request | `<Module>ListRequest` | `TaskListRequest` |
| Read port (Protocol) | `<Module>ReadPort` | `TaskReadPort` |

## Hard Rules (Enforced by Tests)

These constraints are tested in `backend/modular_backend/tests/test_architecture_constraints.py` and must never be violated:

1. **Controllers never import `db_models`** — controller talks only to manager
2. **Managers never import `fastapi`** — business logic is framework-agnostic
3. **`db_models` never imports `fastapi`** — persistence is framework-agnostic
4. **No compatibility alias subclasses** — no `class Foo(BarRestController):` patterns
5. **Target model files must be Pydantic-based** — no `@dataclass` in request/response/interface files for auth, communications, entities, views modules
6. **Every module with `controller.py` must have `manager.py` and `db_models.py`** — except modules in `OPTIONAL_DB_MODEL_MODULES`

## Controller Pattern

Reference: `backend/modular_backend/tasks/controller.py`

- Class-based with `__init__(self, manager, database_service_manager=None, auth_service_manager=None)`
- `prepare(self, app: APIRouter, security: Depends | None = None) -> None` registers all routes
- Each route method wraps the manager call in a `tracer.start_as_current_span()` block
- Actor injection via `Depends(get_current_actor_with_roles(WRITE_ALLOWED_ROLES))` or `READ_ALLOWED_ROLES`
- Standard exception cascade in every endpoint (order matters):
  - `HTTPException` — re-raise as-is
  - `RecordNotFoundException`, `NotFoundError` -> 404
  - `ValidationError`, `ValueError` -> 400
  - `AuthorizationError`, `PermissionError` -> 403
  - `ConflictError` -> 409
  - `DBException`, `PersistenceError`, `ServiceError` -> 500
  - `Exception` (catch-all) -> 500 with generic message

## Manager Pattern

Reference: `backend/modular_backend/tasks/manager.py`

- `__init__` receives db_model_service, database_service_manager, config, and optional cross-module managers
- Lifecycle hooks: `start()` / `stop()` — called by `main.py` lifespan
- `get_status() -> <Module>StatusResponse` — returns module name, status, started flag
- Actor-aware methods (`*_for_actor`) extract `organization_id` and `user_id` from actor dict using `_require_actor_field()`
- Exception handling: let known exceptions (`ValidationError`, `AuthorizationError`, `NotFoundError`) pass through; wrap unknown exceptions in `ServiceError`
- Cross-module calls only via injected manager references (e.g., `communications_service_manager`)
- Converts persistence output (`TaskContract`) to response models (`TaskReadResponse`) via `_to_read_response()`

## DB Models Pattern

Reference: `backend/modular_backend/tasks/db_models.py`

- SQLAlchemy model inherits from `Base` (from `database.manager`)
- UUID string PKs: `Column(String(36), primary_key=True, default=lambda: str(uuid4()))`
- `organization_id` column on every table (multi-tenancy)
- `created_at` with `server_default=func.now()`, `updated_at` with `onupdate=func.now()`
- `TaskRecord` dataclass for in-memory fallback storage
- `<Module>ModelService` class with:
  - `__init__(self, database_service_manager)` — sets up DB connection or falls back to in-memory
  - `_use_memory() -> bool` — checks if DB is available
  - `_session() -> Session` — gets DB session or raises `PersistenceError`
  - Dual-path methods: in-memory dict operations or SQLAlchemy queries
  - All methods return `<Module>Contract` (from `models/interface.py`)
  - Wrap all exceptions in `PersistenceError`
- `_to_contract(record)` and `_to_contract_from_model(model)` static methods for conversion

## Models Directory

### request.py

Reference: `backend/modular_backend/tasks/models/request.py`

- Inherit from `common.data_model.BaseModel` (Pydantic v2)
- Use `Field(...)` for required fields with validation (`min_length`, `max_length`)
- Use `@model_validator(mode="after")` for field normalization (strip, uppercase)
- Provide `from_dict(cls, payload) -> Self` classmethod that wraps `model_validate` and raises `ValidationError`

### response.py

Reference: `backend/modular_backend/tasks/models/response.py`

- Inherit from `common.data_model.BaseModel`
- Use `model_config = ConfigDict(from_attributes=True)` on read responses
- Status response always has: `module: str`, `status: str`, `started: bool`
- List response always has: `items: list[<ReadResponse>]`, `total: int`

### interface.py

Reference: `backend/modular_backend/tasks/models/interface.py`

- Domain enums as `str, Enum` classes (e.g., `TaskStatus`, `TaskPriority`, `TaskSource`)
- Contract model with `ConfigDict(frozen=True)` for immutability
- `Protocol` classes for cross-module dependency inversion (e.g., `TaskReadPort`)

## Import Convention

All modules use a dual try/except import pattern for package vs. relative imports:

```python
try:
    from common.logger import logger, tracer
except ImportError:  # pragma: no cover - package import fallback
    from backend.modular_backend.common.logger import logger, tracer
```

This allows modules to work both when run as packages (production) and when imported from test files.

## Shared Infrastructure

- `common/auth.py` — `get_current_actor_with_roles()`, `READ_ALLOWED_ROLES`, `WRITE_ALLOWED_ROLES`
- `common/logger.py` — `logger` and `tracer` singletons
- `common/data_model.py` — base `BaseModel` (Pydantic v2 with `from_attributes=True`, `populate_by_name=True`)
- `common/enums.py` — `ModuleStatus` enum
- `database/manager.py` — `DatabaseServiceManager`, `Base` (SQLAlchemy declarative base)
- `exceptions/base.py` — `ValidationError`, `ServiceError`, `AuthorizationError`, `NotFoundError`, `ConflictError`, `PersistenceError`
- `exceptions/db.py` — `DBException`, `RecordNotFoundException`

## Wiring a New Module in main.py

Reference: `backend/modular_backend/main.py` (see `_setup_generic_modules()`)

Steps in `_setup_generic_modules()`:

1. Import the module's controller, db_models, and manager at the top of `main.py`
2. Instantiate the db model service: `<module>_db_model_service = <Module>ModelService(database_service_manager)`
3. Instantiate the manager: `<module>_service_manager = <Module>ServiceManager(<module>_db_model_service, database_service_manager, config, ...)`
4. Register the controller: `_prepare_controller(app_router, <Module>RestController(<module>_service_manager, database_service_manager=..., auth_service_manager=...))`
5. Track the manager: `managed_services.append(<module>_service_manager)`

If the new module depends on another module's manager, pass it as a constructor argument (e.g., tasks depends on communications).

## Legacy Route Aliases

When a module replaces an existing capability, provide backward-compatible route aliases. Register duplicate routes in `controller.py` with the legacy path alongside the canonical path:

```
# Canonical
GET /tasks/status

# Legacy alias
GET /task_management/status
```

Reference: see `backend/modular_backend/auth/controller.py` for dual-path registration pattern (auth + identity_access aliases).

## Adding a New Module Checklist

1. Create `backend/modular_backend/<module>/` directory
2. Create `__init__.py`
3. Create `models/__init__.py`, `models/request.py`, `models/response.py`, `models/interface.py`
4. Create `db_models.py` — SQLAlchemy model + `<Module>Record` dataclass + `<Module>ModelService` class
5. Create `manager.py` — `<Module>ServiceManager` with `start()`, `stop()`, `get_status()`, business methods
6. Create `controller.py` — `<Module>RestController` with `prepare()` method, standard exception cascade
7. Wire in `main.py`:
   - Add imports at top
   - Add instantiation in `_setup_generic_modules()`
   - Add to `managed_services`
8. Add test file: `backend/modular_backend/tests/test_<module>_module.py`
9. Run architecture constraint tests: `cd backend && python -m pytest modular_backend/tests/test_architecture_constraints.py -v`

## Testing Pattern

Reference: `backend/modular_backend/tests/test_tasks_module.py`

### Test file structure

1. **`_build_client()` helper** — wires db_model_service -> manager -> controller -> APIRouter -> FastAPI -> TestClient with `database_service_manager=None` (in-memory fallback)
2. **CRUD flow test** — exercises the full lifecycle (create, list, update, archive) via HTTP client
3. **Status endpoint test** — verifies `GET /<module>/status` returns module info
4. **Manager-level tests** — tests business logic methods directly on the manager (e.g., `apply_side_effects`)

### Test conventions

- Use `from backend.modular_backend.<module>.controller import ...` (absolute import)
- Set actor headers: `x-user-id`, `x-org-id`, `x-user-roles`
- Write roles use `recruiter`/`admin`, read roles use `viewer`
- Assert HTTP status codes explicitly
- Test both success paths and edge cases

### Architecture constraint tests

Always run after adding/modifying a module:

```bash
cd backend && python -m pytest modular_backend/tests/test_architecture_constraints.py -v
```

This validates:
- Module follows controller/manager/db_models layout
- No cross-layer imports
- No legacy subclass patterns
- Pydantic-based contracts where required
