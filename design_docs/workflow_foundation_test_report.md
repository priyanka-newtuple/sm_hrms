# Workflow Foundation Test Report

**Date:** 2026-03-11

## Command
```bash
/Users/dhiraj/github/ai_ats/atsbackend/bin/python -m pytest -q \
  backend/modular_backend/tests/test_workflow_module.py \
  backend/modular_backend/tests/test_tasks_module.py \
  backend/modular_backend/tests/test_architecture_constraints.py
```

## Results
```
12 passed, 13 warnings in 1.04s
```

## Notes
- Added coverage for workflow foundation endpoints (canonical + legacy aliases).
- Re-ran tasks module and architecture constraints as regression checks.

## Docker Verification

**Date:** 2026-03-12

### Environment
- Modular backend run via `docker compose -f docker-compose.modular.yml up --build`
- Endpoint base: `http://localhost:8001`
- Shared Postgres container on `localhost:5454`
- Schema: `modular_backend`

### Live API Checks
```bash
curl -sS http://localhost:8001/health
curl -sS http://localhost:8001/v1/api/workflow/status \
  -H 'x-user-id: user-1' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: admin'
curl -sS -X POST http://localhost:8001/v1/api/state-machines \
  -H 'Content-Type: application/json' \
  -H 'x-user-id: user-1' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: admin' \
  -d '{...}'
curl -sS 'http://localhost:8001/v1/api/state-machines' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS 'http://localhost:8001/v1/api/state-machines/ATS.Application/active' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS 'http://localhost:8001/v1/api/entities/entity-1/transitions/available?machine_name=ATS.Application&current_state=NEW' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS 'http://localhost:8001/v1/api/entities/entity-1/transitions/screen/preflight?machine_name=ATS.Application&current_state=NEW' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS -X POST http://localhost:8001/v1/api/entities/entity-1/transitions \
  -H 'Content-Type: application/json' \
  -H 'x-user-id: user-1' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: admin' \
  -d '{"trigger":"screen"}'
```

### Results
- `GET /health` returned `{"status":"ok"}`
- `GET /v1/api/workflow/status` returned ready status
- `POST /v1/api/state-machines` created `ATS.Application` version `1` for `org-1`
- `GET /v1/api/state-machines` returned the created machine in `items`
- `GET /v1/api/state-machines/ATS.Application/active` returned version `1`
- `GET /v1/api/entities/entity-1/transitions/available?...` returned one available `screen` transition
- `GET /v1/api/entities/entity-1/transitions/screen/preflight?...` returned:
  - `to_state = SCREENING`
  - `all_guards_passed = false`
  - `needs_dialog = true`
  - required field `candidate.resume_url`
  - prime field `candidate.phone`
  - comment requirement metadata
- `POST /v1/api/entities/entity-1/transitions` returned `501` with deferred execution message

### Notes
- Live Docker verification required adding workflow permission mappings in the modular auth manager.
- The created row was also verified directly in Postgres under `modular_backend.workflow_state_machines`.

## Re-Verification

**Date:** 2026-03-18

### Unit Test Environment
- Local virtualenv aligned with `backend/modular_backend/requirements.txt`
- `PYTHONPATH` set to:
  - `/Users/dhiraj/github/ai_ats/backend/modular_backend`
  - `/Users/dhiraj/github/ai_ats`

### Unit Test Command
```bash
PYTHONPATH=/Users/dhiraj/github/ai_ats/backend/modular_backend:/Users/dhiraj/github/ai_ats \
  /Users/dhiraj/github/ai_ats/.venv/bin/python -m pytest \
  backend/modular_backend/tests/test_workflow_module.py -q
```

### Unit Test Results
```text
3 passed, 6 warnings in 1.90s
```

### Unit Test Warnings
- `pythonjsonlogger.jsonlogger` deprecation warning
- `requests` dependency warning about `urllib3` / `chardet` / `charset_normalizer`
- SQLAlchemy `declarative_base()` moved warning in `backend/modular_backend/database/manager.py`
- `datetime.utcnow()` deprecation warning in `backend/modular_backend/workflow/db_models.py`

### Docker Re-Verification

**Date:** 2026-03-18

### Environment
- Modular backend run via `docker compose -f docker-compose.modular.yml up -d --force-recreate`
- Dedicated Postgres container added to `docker-compose.modular.yml`
- Endpoint base: `http://localhost:8001`
- API prefix: `/v1/api`
- Database service: `modular-db`
- Published Postgres port: `5455`
- Schema: `modular_backend`

### Live API Checks
```bash
curl -sS -i http://localhost:8001/v1/api/workflow/status
curl -sS -i -X POST http://localhost:8001/v1/api/workflow/state-machines \
  -H 'content-type: application/json' \
  -H 'x-user-id: user-1' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: admin' \
  --data '{...}'
curl -sS -i 'http://localhost:8001/v1/api/state-machines/ATS.Application/active' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS -i 'http://localhost:8001/v1/api/state-machines/ATS.Application/1' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS -i 'http://localhost:8001/v1/api/entities/entity-1/transitions/available?machine_name=ATS.Application&current_state=NEW' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS -i 'http://localhost:8001/v1/api/entities/entity-1/transitions/screen/preflight?machine_name=ATS.Application&current_state=NEW' \
  -H 'x-user-id: user-2' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: viewer'
curl -sS -i -X POST 'http://localhost:8001/v1/api/entities/entity-1/transitions' \
  -H 'content-type: application/json' \
  -H 'x-user-id: user-1' \
  -H 'x-org-id: org-1' \
  -H 'x-user-roles: admin' \
  --data '{"trigger":"screen"}'
```

### Live API Results
- `GET /v1/api/workflow/status` returned `200` with `{"module":"workflow","status":"ready","started":true}`
- `POST /v1/api/workflow/state-machines` returned `201` and created `ATS.Application` version `1` for `org-1`
- `GET /v1/api/state-machines/ATS.Application/active` returned `200` with version `1`
- `GET /v1/api/state-machines/ATS.Application/1` returned `200`
- `GET /v1/api/entities/entity-1/transitions/available?...` returned `200` with one available `screen` transition
- `GET /v1/api/entities/entity-1/transitions/screen/preflight?...` returned `200` with:
  - `to_state = SCREENING`
  - `all_guards_passed = false`
  - `needs_dialog = true`
  - required field `candidate.resume_url`
  - prime field `candidate.phone`
  - comment requirement metadata
- `POST /v1/api/entities/entity-1/transitions` returned `501` with deferred execution message

### Notes
- The earlier modular runtime failure was caused by `docker-compose.modular.yml` depending on an external Postgres host. Re-verification was performed after adding an in-compose `modular-db` service.
- Modular startup currently logs `Alembic skipped: Missing Alembic configuration path or migration database URL in bootstrap configuration`, but the workflow endpoints exercised above still function because the modular bootstrap path creates the required schema/tables directly.
