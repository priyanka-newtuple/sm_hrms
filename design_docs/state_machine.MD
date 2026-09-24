# State-machine platform core + ATS pack — Detailed Design

## Goal

Build a reusable **workflow runtime** that powers multiple “cockpits” (ATS first, PMO next) by standardizing:

* **Entities** (typed domain records)
* **State machines** (explicit lifecycle + guards)
* **Events / timeline** (audit + replay)
* **Transitions** (success/fail + guard evaluation)
* **Signals** (SLAs, timers, thresholds)
* **Interventions** (HITL approvals/overrides)
* **Orchestrations** (long-running playbooks executed by agents/tools/humans)

The product ships as **domain cockpits** (ATS, PMO, etc.). Customers should feel they are buying an outcome-focused app, not a “workflow builder.”

---

## Non-goals

* Do not build a full BPMN designer.
* Do not allow unrestricted customer-defined states/transitions in v1.
* Do not attempt to replace full enterprise SoR (Workday/Greenhouse) in v1.

---

## Architecture overview

### Layers

1. **Platform Core (generalized)**

* Data model: entities, relations, current state, events, transitions, interventions, signals
* Runtime: state machine executor + guard engine + idempotency
* Orchestration runner: step execution + retries + correlation ids
* Observability: timeline, traces, costs

2. **Domain Packs (ATS, PMO, …)**

* Entity type schemas (ATS.Job, ATS.Candidate, ATS.Application)
* State machine definitions (ATS.Application.lifecycle)
* Playbooks (screening, scheduling, offer)
* Projections for UI (pipeline board, SLA heatmap)
* Connectors (ATS, calendars, assessments)

### Service Layer Separation

Services must maintain clear boundaries between platform capabilities and domain-specific logic. The dependency direction is always: **Domain → Core** (never Core → Domain).

#### Pattern: Generic Capability + Domain Interpreter

Many features have both generic and domain-specific aspects. Split them accordingly:

| Platform Core (Generic) | Domain Pack (Skin-Specific) |
|------------------------|----------------------------|
| Document upload & storage | Resume interpretation → Candidate fields |
| PDF/DOCX text extraction | Document → domain entity mapping |
| Background job processing | Domain-specific job handlers |
| File storage service | Domain-specific file validators |
| LLM/AI service abstraction | Domain-specific prompts & schemas |

**Example: Document Import**

```
Platform Core:
├── file_storage_service.py        # Store/retrieve any file
├── document_extraction_service.py # Extract text from PDF/DOCX
├── background_job_service.py      # Queue and track async work

Domain Pack (ATS):
├── resume_interpreter.py          # Text → candidate fields (name, skills, experience)
├── candidate_import_service.py    # Create ATS.Candidate, detect duplicates

Domain Pack (PMO):
├── scope_interpreter.py           # Text → project milestones, deliverables
├── project_import_service.py      # Create PMO.Project from parsed scope doc
```

**Frontend Equivalent:**

```
core/services/api.ts       → Generic document upload endpoints
domains/ats/services/api.ts → Resume interpretation + candidate creation
```

#### Dependency Rules

1. **Core types cannot import from domain types** - If a type is needed in core, it belongs in core.
2. **Core services cannot reference domain entity types** - Use configuration/injection instead of hardcoded `ATS.Application` checks.
3. **Projections are domain-specific** - `AtsPipelineView` belongs in domain pack, not core.
4. **Domain services can import from core** - This is the correct direction.

---

## Data model (platform core)

### 1) entities

**Purpose:** store typed domain records with schema versioning.

Fields:

* `entity_id` (uuid, PK)
* `entity_type` (text) e.g., `ATS.Application`, `PMO.Project`
* `schema_name` (text) e.g., `ats_application`
* `schema_version` (int)
* `data` (jsonb)
* `owner_id` (text, optional)
* `created_at`, `updated_at`, `archived_at`

Notes:

* `data` holds domain attributes (candidate profile, job details, etc.)
* Use `schema_name + schema_version` to validate and evolve data.

### 2) entity_relations

**Purpose:** represent entity graph edges (candidate → application → job).

Fields:

* `relation_id` (uuid, PK)
* `from_entity_id`, `from_entity_type`
* `to_entity_id`, `to_entity_type`
* `relation_type` (text) e.g., `APPLIED_TO`, `BELONGS_TO`, `HAS_OFFER`
* `metadata` (jsonb)
* `created_at`

Indexes:

* `(from_entity_type, from_entity_id)`
* `(to_entity_type, to_entity_id)`

### 3) entity_state

**Purpose:** current lifecycle pointer per entity (only for entities with state machines).

Fields:

* `entity_id` (uuid, PK)
* `entity_type` (text)
* `machine_name` (text)
* `machine_version` (int)
* `state` (text)
* `state_entered_at` (timestamptz)
* `state_version` (int) optimistic lock
* `last_activity_at` (timestamptz)
* `sla_due_at` (timestamptz, optional)
* `risk` (text enum-ish)

Notes:

* `state_version` increments on every successful transition.
* `sla_due_at` is a denormalized pointer used for fast queries.

### 4) entity_events (append-only)

**Purpose:** immutable audit + UI timeline + replay.

Fields:

* `event_id` (uuid, PK)
* `entity_id`, `entity_type`
* `event_type` (text) e.g., `application.applied`, `offer.approved`
* `actor_type` (HUMAN | AGENT | SYSTEM | INTEGRATION)
* `actor_id` (text)
* `correlation_id` (uuid)
* `idempotency_key` (text)
* `payload` (jsonb)
* `occurred_at` (timestamptz)

Notes:

* Everything user-visible should be explainable via events.

### 5) state_transitions

**Purpose:** debug-friendly log of transition attempts (including failures).

Fields:

* `transition_id` (uuid, PK)
* `entity_id`, `entity_type`
* `from_state`, `to_state`
* `trigger` (text) command name
* `actor_type`, `actor_id`
* `status` (SUCCESS | FAILED)
* `failure_code` (INVALID_STATE | GUARD_FAILED | PERMISSION | TOOL_ERROR)
* `failure_detail` (text)
* `guard_report` (jsonb)
* `inputs` (jsonb)
* `outputs` (jsonb)
* `correlation_id` (uuid)
* `occurred_at`

Notes:

* This table is the “why did it not move?” answer.

### 6) interventions (HITL)

**Purpose:** approvals/overrides/pauses that humans can act on.

Fields:

* `intervention_id` (uuid, PK)
* `entity_id`, `entity_type`
* `kind` (APPROVAL | OVERRIDE | PAUSE | RESUME | EDIT | FORCE_TRANSITION)
* `requested_by`, `assigned_to`
* `status` (PENDING | APPROVED | REJECTED | CANCELLED | EXPIRED)
* `request_payload`, `decision_payload`
* `reason`
* `requested_at`, `decided_at`

### 7) signals

**Purpose:** timers and rule-based triggers (SLA, stale, risk alerts).

Fields:

* `signal_id` (uuid, PK)
* `entity_id`, `entity_type`
* `signal_type` (text)
* `due_at` (timestamptz)
* `status` (PENDING | FIRED | CANCELLED)
* `target_playbook` (text)
* `payload` (jsonb)
* `fired_at`, `created_at`

---

## State machine definition model

### state_machines

**Purpose:** store versioned state machine DSL.

Fields:

* `machine_name` (text)
* `version` (int)
* `is_active` (bool)
* `definition` (jsonb)
* `created_at`

Definition JSONB shape (suggested):

* `states`: list of state names + metadata
* `initial_state`
* `transitions`: list of

  * `trigger`
  * `from` (one or many)
  * `to`
  * `guards` (list)
  * `side_effects` (list; emits events, schedules signals, starts playbooks)
* `terminal_states` (optional)

Guard model:

* `type`: `FIELD_PRESENT`, `RELATION_EXISTS`, `POLICY_CHECK`, `EXTERNAL_CHECK`, `HITL_REQUIRED`
* `params`: JSON

---

## Runtime: transition execution

### Responsibilities

* Validate trigger is allowed from current state.
* Evaluate guards.
* If guards pass, atomically:

  * update `entity_state` (state + timestamps + version)
  * append `entity_events`
  * write `state_transitions`
  * schedule/unschedule `signals` (if configured)
  * optionally kick off a playbook

### Concurrency + idempotency

* Use `state_version` optimistic locking:

  * read `(state, state_version)`
  * update `entity_state` with `WHERE state_version = :expected`
  * on 0 rows updated → retry or return conflict
* Use `idempotency_key` on external webhook-driven triggers.

### Failure handling

* Always write a FAILED row into `state_transitions`.
* Emit an `entity_event` for failure only when useful for UI.
* If an external tool fails, set failure_code=TOOL_ERROR and include tool metadata.

---

## Orchestrations (playbooks)

### Why separate from state machine

* State machine defines allowed movements.
* Playbooks define *how* work happens (agents/tools/humans) and may span time.

### playbooks table (optional)

* `playbook_name`, `version`, `definition` (jsonb)

### playbook runs (runtime)

* `run_id`
* `playbook_name`, `version`
* `correlation_id`
* `entity_id`, `entity_type`
* `status` (RUNNING/SUCCEEDED/FAILED/PAUSED)
* step-level records (optional) or store in events

### Step types

* `AGENT_CALL` (LLM reasoning + tool use)
* `TOOL_CALL` (calendar, ATS writeback)
* `HITL_WAIT` (pause until intervention resolved)
* `TIMER_WAIT`

---

## Projections (domain-friendly read models)

Because JSONB entities are flexible but not ideal for fast analytics, use projections:

### Example projections for ATS

* `ats_pipeline_view` (job_id, application_id, candidate_name, state, sla_due_at, risk)
* `ats_sla_heatmap` (job_id, state, count, breached_count, avg_time_in_state)

Implementation options:

* Materialized views refreshed on schedule
* Projection tables updated by event consumers

---

## ATS Domain Pack (v1)

### Entity types

* `ATS.Job`
* `ATS.Candidate`
* `ATS.Application`

### Relationships

* Candidate `APPLIED_TO` Application
* Application `FOR_JOB` Job
* Application `HAS_INTERVIEW` Interview (optional as entity)
* Application `HAS_OFFER` Offer (optional as entity)

### Application lifecycle state machine (canonical)

States:

* `APPLIED`
* `SCREENING`
* `ASSIGNMENT`
* `PANEL`
* `OFFER`
* `BGV`
* `JOINED`
  Terminal:
* `REJECTED`, `WITHDRAWN`

Key triggers (subset)

* `start_screening` APPLIED→SCREENING
* `screen_pass` SCREENING→ASSIGNMENT (guard: score>=threshold OR override)
* `assignment_pass` ASSIGNMENT→PANEL
* `panel_pass` PANEL→OFFER (guard: panel_feedback=pass)
* `offer_accepted` OFFER→BGV
* `bgv_clear` BGV→JOINED
* `reject` any→REJECTED (guard: reason present)
* `withdraw` any→WITHDRAWN

### ATS playbooks (v1)

* Screening playbook (runs in SCREENING)
* Scheduling playbook (runs in PANEL)
* Offer approval playbook (runs in OFFER with HITL)

### Signals (ATS)

* `STALE_IN_STATE_48H` → nudge owner in Slack
* `SLA_BREACH_24H` → escalate to hiring manager
* `SCHEDULING_RISK` → run scheduling playbook

### Interventions (ATS)

* Override screening score
* Force transition
* Approve compensation
* Pause application

---

## Customization strategy (avoid BPM engine trap)

Allowed configuration (safe):

* SLA durations per state
* Routing rules (which recruiter/panelist)
* Guard thresholds (screen score cutoff)
* Which playbooks are enabled

Not allowed in v1:

* Customer-defined states
* Customer-defined arbitrary transitions

Escape hatch:

* Allow tags/flags (e.g., `needs_exec_review=true`) without changing state names.

---

## Integration strategy (Light SoR)

### Principles

* External ATS remains the truth for some fields.
* Dialogtuple owns workflow truth: lifecycle + timeline + interventions.

### Sync model

* Store `external_*_key` inside entity `data`.
* Inbound webhooks create `entity_events` and may trigger transitions.
* Outbound writebacks happen via playbooks with idempotency keys.

Conflict handling

* Field-level ownership: each field is either “ours”, “theirs”, or “merged.”
* UI shows conflicts when both sides change within a window.

---

## Security and governance hooks

* RBAC on entity types and interventions.
* PII redaction in event payloads.
* Per-agent and per-playbook budgets.
* Audit log is `entity_events` + `state_transitions`.

---

## Implementation plan (incremental)

1. Build core tables + transition executor + event append
2. Add interventions + signals
3. Add ATS pack (schemas + lifecycle)
4. Add 2–3 playbooks (screening, scheduling, offer approval)
5. Add projections for pipeline + SLA heatmap
6. Add external ATS sync for one target (e.g., Greenhouse)

---

## Open decisions

* JSONB-only entities vs hybrid (promote hot fields into projection tables).
* Orchestration runtime: lightweight runner vs Temporal/Camunda.
* Multi-tenant isolation model (schema-per-tenant vs row-level tenant_id).
