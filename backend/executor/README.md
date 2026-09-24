# Executor Module

Self-contained pluggable executor framework for the Newtuple workflow engine. The executor module defines the contract for all workflow actions, owns the executor registry, resolves `$entity.*` config placeholders at runtime, and routes executor outcomes to workflow transition triggers. New action types are added by implementing `BaseExecutor` and registering the class — no changes to the workflow engine are needed.

---

## Module Structure

```
executor/
├── controller.py           REST endpoints (ExecutorRestController)
├── manager.py              Registry, execution, and trigger resolution (ExecutorServiceManager)
├── models/
│   ├── interface.py        Core contracts (BaseExecutor, ExecutorInput, ExecutorResponse, ExecutorBinding, etc.)
│   ├── request.py          Inbound schemas (ExecutorExecutionRequest)
│   └── response.py         Outbound schemas (ExecutorCatalogResponse, ExecutorExecutionResponse)
└── executors/
    ├── base.py             Shared utilities (get_field, fail, apply_template_placeholders, get_frontend_url)
    ├── send_email.py       SendEmailExecutor      — mail.send_email
    ├── send_approval.py    SendApprovalExecutor   — mail.send_approval
    └── receive_data.py     ReceiveDataExecutor    — form.receive_data
```

---

## Built-in Executors

### `mail.send_email`

Sends an email using a stored template or inline subject/body. Immediately fires the outcome trigger on success.

**Config fields**

| Field         | Required | Description |
|---------------|----------|-------------|
| `to`          | yes      | Recipient email address. Supports `$entity.*` placeholders. |
| `template_id` | no       | UUID of a stored email template. Subject and body are loaded from the template. |
| `subject`     | no       | Email subject (used if no template, or overrides template subject). |
| `body_html`   | no       | HTML body (used if no template, or overrides template body). |
| `form_id`     | no       | When set and the body contains `{{form_link}}`, the run parks in `pending_external`. |

**Template placeholders**

| Placeholder      | Replaced with |
|------------------|---------------|
| `{{field_name}}` | Value of `field_name` from the resolved executor fields |
| `{{form_link}}`  | Signed JWT URL pointing to the public form page |

**Outcomes:** `sent`, `failed`

**External wait:** Only when `form_id` is set and `{{form_link}}` appears in the body. The workflow trigger fires immediately (`fire_trigger_immediately=true`) but the run stays `pending_external` so the form submission can be tracked.

---

### `mail.send_approval`

Sends an approval email with embedded one-click approve / reject links. Always waits in `pending_external` until the approver responds.

**Config fields**

| Field         | Required | Description |
|---------------|----------|-------------|
| `to`          | yes      | Approver email address. Supports `$entity.*` placeholders. |
| `template_id` | no       | UUID of a stored email template. |
| `subject`     | no       | Email subject. |
| `body_html`   | no       | HTML body. |
| `form_id`     | no       | Used to fetch the form schema for displaying submitted field labels in the approval email. |

**Template placeholders**

| Placeholder          | Replaced with |
|----------------------|---------------|
| `{{approve_link}}`   | One-click approval URL |
| `{{reject_link}}`    | One-click rejection URL |
| `{{submitted_data}}` | HTML table of submitted form fields from the latest `form.receive_data` run |

**Outcomes:** `approved`, `rejected`, `failed`, `pending`

**External wait:** Always (`is_external_wait=true`, `fire_trigger_immediately=false`). The run stays `pending_external` until `POST /approvals/public/{run_id}/respond` is called.

---

### `form.receive_data`

Pauses the workflow and waits for an external form submission. No email is sent — the form link is typically delivered by a prior `mail.send_email` step.

**Config fields**

| Field           | Required | Default | Description |
|-----------------|----------|---------|-------------|
| `form_id`       | yes      | —       | `schema_key` of the form schema to display |
| `timeout_hours` | no       | `24`    | How long to wait before the run is timed out |

**Outcomes:** `waiting`, `received`, `failed`

**External wait:** Always. The run is marked `pending_external` until a form submission arrives at the public form endpoint.

---

## Placeholder Resolution

Before an executor runs, the manager resolves `$entity.*` placeholders in the config using the live entity data:

```json
{ "to": "$entity.clientemail" }
→ { "to": "john@example.com" }
```

Nested dicts and lists are resolved recursively. A `ValidationError` is raised if a referenced field does not exist on the entity.

---

## Execution Flow

```
WorkflowEngine
    ↓ state has on_state_action
BackgroundJobsManager._execute_action_run()
    ↓ resolve $entity.* placeholders
ExecutorServiceManager.execute_executor(request)
    ↓ look up executor by name
BaseExecutor.execute(input_payload)
    ↓ returns ExecutorResponse
ExecutorServiceManager.resolve_trigger_for_outcome(result, binding)
    ↓ maps outcome → transition trigger
BackgroundJobsManager._fire_trigger()
```

---

## Key Interfaces

### `ExecutorInput`

What every executor receives:

```
ExecutorInput
├── entity_id       string   UUID of the entity
├── entity_type     string   Type of the entity
├── current_state   string   Current workflow state name
├── fields          dict     Resolved config fields (after placeholder substitution)
└── context         dict     Additional runtime context
```

### `ExecutorResponse`

What every executor must return:

```
ExecutorResponse
├── success                  bool          Whether execution succeeded
├── message                  string        Human-readable result summary
├── data                     ExecutorData  Outcome + output fields + meta
├── is_external_wait         bool          True if the run should park in pending_external
├── fire_trigger_immediately bool          True if the trigger fires despite external wait
└── timeout_hours            int           How long before the pending_external run times out
```

### `ExecutorBinding`

How the workflow wires an executor to transitions:

```json
{
  "executor_name": "mail.send_email",
  "config": { "to": "$entity.clientemail", "template_id": "..." },
  "outcome_triggers": {
    "sent": "INITIAL_to_STATE_2",
    "failed": "INITIAL_to_STATE_3"
  }
}
```

---

## Implementing a Custom Executor

1. Subclass `BaseExecutor` and implement `definition` and `execute()`.
2. Return `ExecutorResponse` with a valid outcome from `definition.supported_outcomes`.
3. Use `fail(message)` from `executors/base.py` to return a clean failure response.
4. Add the class to `_EXECUTOR_CLASSES` in `manager.py`.

```python
from executor.executors.base import fail, get_field
from executor.models.interface import (
    BaseExecutor, ExecutorData, ExecutorDefinition, ExecutorInput, ExecutorResponse,
)

class MyExecutor(BaseExecutor):
    @property
    def definition(self) -> ExecutorDefinition:
        return ExecutorDefinition(
            name="my.action",
            description="Does something useful.",
            supported_outcomes=["done", "failed"],
        )

    def execute(self, input_payload: ExecutorInput, db=None) -> ExecutorResponse:
        try:
            value = get_field(input_payload.fields, "some_field")
            if not value:
                return fail("missing required field: some_field")
            # ... do work ...
            return ExecutorResponse(
                success=True,
                message="Done",
                data=ExecutorData(outcome="done", fields={}, meta={}),
            )
        except Exception as exc:
            return fail(str(exc))
```

---

## Design Principles

- **Executor = decision.** Executors return business outcomes, not workflow instructions.
- **Binding = routing.** The `ExecutorBinding` maps outcomes to triggers — executors never know about states.
- **Workflow = movement.** The workflow engine reads the trigger and performs the state transition.
- **Separation of concerns.** Business logic, routing config, and state management are fully decoupled.

---

## Testing

Primary test file: `backend/tests/test_executor_module.py`

```bash
cd backend
pytest tests/test_executor_module.py
```
