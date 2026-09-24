# Tools Module Test Report

## Scope

Module under test:
- `backend/modular_backend/tools`

Test package:
- `backend/modular_backend/tests/tools_module`

Execution date:
- 2026-03-19

## Commands Run

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m pytest backend/modular_backend/tests/tools_module -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile \
  backend/modular_backend/tools/controller.py \
  backend/modular_backend/tools/manager.py \
  backend/modular_backend/tools/db_models.py \
  backend/modular_backend/tools/models/interface.py \
  backend/modular_backend/tools/models/request.py \
  backend/modular_backend/tools/models/response.py
```

## Result

- Status: Passed
- Tests passed: 22
- Tests failed: 0
- Warnings: 2

## Coverage Summary

The split `tools` suite currently covers:
- controller behavior for catalog, preset, execution, document-config-alias, and execution-history endpoints
- manager behavior for runtime tool validation, modular execution, modular-backend-owned platform execution, unsupported-tool rejection, and actor-scoped execution-history reads
- manager-level execution coverage for every public tool name currently exposed by the shared catalog
- DB-backed persistence for `tool_execution_logs`
- execution-history filtering by tool, source, success, and backend
- admin-only access to execution-history routes
- entity metadata inference in execution logs
- modular document/schema/picklist/event tool flows that do not depend on `backend/app/**`

## APIs Validated

HTTP routes covered by tests:
- `GET /tools/catalog`
- `GET /tools/catalog/{tool_name}`
- `GET /tools/presets`
- `GET /tools/presets/{preset_name}`
- `POST /tools/execute`
- `GET /tools/executions`
- `GET /tools/executions/{execution_id}`
- `GET /config/document-types/tools`
- `GET /config/document-types/tools/presets`

Manager functions covered by tests:
- `get_catalog()`
- `get_tool_descriptor()`
- `get_presets()`
- `get_preset()`
- `validate_tool_names()`
- `validate_runtime_tools()`
- `build_runtime_tools()`
- `execute_tool()`
- `execute_tool_for_actor()`
- `list_executions_for_actor()`
- `get_execution_for_actor()`

Persistence methods covered by tests:
- `create_execution_log()`
- `list_execution_logs()`
- `get_execution_log()`

## Current Supported Tool Surface

The current modular `tools` catalog now exposes only tools that are implemented inside `backend/modular_backend` today:

- `read_document`
- `get_form_schema`
- `get_picklist_values`
- `list_events`
- `add_stage_comment`
- `list_entity_types`
- `send_calendar_invite`

Tools that are not yet implemented inside modular backend are no longer advertised as available by the current catalog/runtime projection.

## Notes

Warnings observed during execution:
- `pythonjsonlogger` deprecation warning
- SQLAlchemy `declarative_base()` deprecation warning from the shared database manager

The module now:
- uses real DB-backed execution-history persistence
- no longer exposes lifecycle/status endpoints
- no longer depends on `backend/app/**` for tool execution
- only advertises tools that currently work inside modular backend

## Regression Context

This suite was rerun as part of the combined runtime-module regression command and passed within the `65 passed` total.
