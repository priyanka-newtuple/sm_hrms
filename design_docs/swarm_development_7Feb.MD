# Swarm Development Grooming — 7 Feb 2026

Feature requests and bugs raised by Shilpa, Vikas, and team. Groomed and ready for parallel agent execution.

**Current Alembic head:** `041` — new migrations start at `042`.

---

## Dependency Graph

```
SWARM-06 ─────blocks────→ SWARM-07  (both modify document_service.py)
SWARM-06 ─────blocks────→ SWARM-01  (import needs correct tenant scoping)
SWARM-03 ─────blocks────→ SWARM-09  (both modify funnel builder + transition system)
SWARM-09 ─────blocks────→ SWARM-08  (backward movement cancel logic for rejection emails)
SWARM-04 ───overlaps───→ SWARM-01  (both add entries to tenant_provisioning_service.py)
```

## File Conflict Matrix

Files touched by multiple tickets — determines which tickets **cannot** run in parallel.

| Shared File | Tickets | Conflict Type |
|-------------|---------|---------------|
| `document_service.py` | SWARM-06, SWARM-07 | Both modify same functions |
| `transition_service.py` | SWARM-03, SWARM-08, SWARM-09 | Side effects, preflight, loop detection |
| `FunnelBuilder/TransitionsStep.tsx` | SWARM-03, SWARM-09 | Both add transition config UI |
| `ApplicationDetailPanel.tsx` | SWARM-03, SWARM-07, SWARM-08, SWARM-09 | Transition dialog, links, send email, backward buttons |
| `tenant_provisioning_service.py` | SWARM-01, SWARM-04 | Both add default agents/doc types |
| `document_config_service.py` | SWARM-01, SWARM-04 | Both add DEFAULT_DOCUMENT_TYPES entries |
| `standard_funnel.py` | SWARM-03, SWARM-09 | Transition definitions |
| `guard_service.py` | SWARM-03, SWARM-06 | Preflight eval + org_id fix |
| `mcp_server.py` | SWARM-01, SWARM-04 | New agent tools |

---

## Priority Waves

### Wave P1 — 5 tickets in parallel (no file conflicts between them)

| Done | Ticket | Agent | Branch | Status |
|------|--------|-------|--------|--------|
| [x] | **SWARM-06** — Multi-tenancy fix | agent1 | `fix/swarm-06-multitenant` | Complete |
| [x] | **SWARM-03** — Transition popup | agent2 | `feat/swarm-03-transition-dialog` | Complete |
| [ ] | **SWARM-02** — Email forwarding | agent3 | `feat/swarm-02-email-forward` | Ready for review |
| [ ] | **SWARM-05** — Resume performance | agent3 | `feat/swarm-05-resume-perf` | In progress |
| [x] | **SWARM-04** — JD upload | agent3 | `feat/swarm-04-jd-upload` | Complete |

### Wave P2 — 3 tickets in parallel (after P1 merges)

| Done | Ticket | Agent | Branch | Blocked By | Status |
|------|--------|-------|--------|------------|--------|
| [ ] | **SWARM-09** — Backward movement | _______________ | `feat/swarm-09-backward-movement` | SWARM-03 | Not started |
| [ ] | **SWARM-07** — Multiple assignments + links | _______________ | `feat/swarm-07-multi-assignments` | SWARM-06 | Not started |
| [ ] | **SWARM-01** — CSV/Excel import | _______________ | `feat/swarm-01-csv-import` | SWARM-04, SWARM-06 | Not started |

### Wave P3 — 1 ticket (after P2 merges)

| Done | Ticket | Agent | Branch | Blocked By | Status |
|------|--------|-------|--------|------------|--------|
| [ ] | **SWARM-08** — Rejection email | _______________ | `feat/swarm-08-rejection-email` | SWARM-09 | Not started |

---
---

## SWARM-06: Multi-Tenancy Bug — Cross-Tenant Data Leak

| | |
|---|---|
| **Wave** | **P1** |
| **Type** | Bug — Security |
| **Priority** | HIGH — fast-track |
| **Reporter** | Team (Shilpa uploaded resume in Infotech Works, detected as duplicate from Newtuple tenant) |
| **Migration** | None required |
| **Branch** | `fix/swarm-06-multitenant` |

### Description

When uploading a resume in one organization (Infotech Works), the system incorrectly identifies the candidate as a duplicate from a different organization (Newtuple). Root cause: entity queries across multiple services lack `organization_id` filtering.

### Grooming Decisions

- **Priority:** Fast-track to fix immediately.
- **Scope:** Fix all 19 identified unscoped queries. Full audit completed (see below). Do NOT fix other issues found during audit — raise them only.

### Full Multi-Tenancy Audit Results

19 findings across 9 files (8 CRITICAL, 9 HIGH, 2 MEDIUM):

| # | File | Function | Lines | Severity | org_id Available? |
|---|------|----------|-------|----------|-------------------|
| 1 | `candidate_service.py` | `get_candidate_applications()` | 30-33 | CRITICAL | NO — needs parameter added |
| 2 | `candidate_service.py` | `sync_candidate_data_to_applications()` | 226-229 | CRITICAL | NO — needs parameter added |
| 3 | `candidate_service.py` | `update_candidate_from_resume()` | 141-145 | CRITICAL | NO — needs parameter added |
| 4 | `document_service.py` | `upload_document()` | 130 | CRITICAL | YES — not used |
| 5 | `document_service.py` | `get_document()` | 343 | CRITICAL | YES — not used |
| 6 | `document_service.py` | `get_document_by_storage_key()` | 370 | CRITICAL | YES — not used |
| 7 | `document_service.py` | `list_entity_documents()` | 397 | CRITICAL | YES — not used |
| 8 | `document_service.py` | `delete_document()` | 470 | CRITICAL | YES — not used |
| 9 | `document_service.py` | `update_document_extracted_data()` | 525 | CRITICAL | YES — not used |
| 10 | `comments.py` (route) | `create_entity_comment()` | 80 | HIGH | YES — not used |
| 11 | `entity_service.py` | `get_state()` | 267 | HIGH | OPTIONAL — final query unscoped |
| 12 | `event_service.py` | `list_events()` | 57-60 | HIGH | NO — needs parameter added |
| 13 | `event_service.py` | `find_event_by_idempotency()` | 78-82 | HIGH | NO — needs parameter added |
| 14 | `guard_service.py` | `_evaluate_guard()` RELATION_EXISTS | 149-152 | HIGH | YES — not used |
| 15 | `guard_service.py` | `_evaluate_guard()` HITL_REQUIRED | 192-195 | HIGH | YES — not used |
| 16 | `action_executor.py` | `_execute_add_comment()` | 532 | CRITICAL | YES (`self.org_id`) — not used |
| 17 | `projection_service.py` | `_resolve_related_entity()` | 158, 172 | HIGH | NO — caller has it, doesn't pass |
| 18 | `entity_service.py` | `list_relations()` | 365-371 | MEDIUM | OPTIONAL — query unscoped |
| 19 | `resume_upload.py` (route) | Duplicate detection | 801-830 | CRITICAL | YES — not used |

#### Attack Scenarios

1. **Cross-tenant resume access** — Org A user updates Org B candidates via `update_candidate_from_resume()`
2. **Transition approval bypass** — Cross-org interventions satisfy `HITL_REQUIRED` guards
3. **Comment injection** — Comments attached to any org's entities via `/entities/{id}/comments`
4. **Document theft** — Any org's documents accessible via `document_service.get_document()`

### Acceptance Criteria

- [x] Add `Entity.organization_id == org_id` filter to all 19 identified queries
- [x] For findings 1-3, 12-13, 17: add `org_id` parameter to function signature and update all callers
- [x] For findings 4-10, 14-16, 18-19: use existing `org_id` parameter in query filter
- [ ] Regression tests: create entities in Org A and Org B, verify Org A queries never return Org B data
- [ ] All existing tests pass

### System Design

**Approach:** Add `.filter(Entity.organization_id == org_id)` to all unscoped queries.

**Fix strategy:**
1. Functions where `org_id` is already available but not used (findings 4-10, 14-16, 18-19): add filter to existing queries
2. Functions where `org_id` parameter is missing (findings 1-3, 12-13, 17): add `org_id` parameter, update all callers
3. Add multi-tenant regression tests

**Files to modify:** `document_service.py`, `candidate_service.py`, `comments.py`, `entity_service.py`, `event_service.py`, `guard_service.py`, `action_executor.py`, `projection_service.py`, `resume_upload.py`

### Agent Feedback

> Agent: agent1

**Started:** 2026-02-07
**Completed:** 2026-02-07
**Notes:**

```
PASS 1: Fixed all 19 identified unscoped queries across 9 files.

Files modified (9):
1. candidate_service.py — Added org_id param to get_candidate_applications(),
   update_candidate_from_resume(), sync_candidate_data_to_applications() + org_id filter
2. document_service.py — Added org_id filter to upload_document(), get_document(),
   get_document_by_storage_key(), list_entity_documents(), delete_document(),
   update_document_extracted_data()
3. comments.py — Added organization_id filter to entity lookup in create_entity_comment()
4. event_service.py — Added org_id param/filter to list_events(), find_event_by_idempotency()
5. guard_service.py — Added organization_id filter to RELATION_EXISTS and HITL_REQUIRED guards
6. action_executor.py — Added organization_id filter to entity lookup in _execute_add_comment()
7. projection_service.py — Added org_id param to _resolve_related_entity() and
   _build_denormalized_data(), scoped relation and entity lookups
8. resume_upload.py — Added organization_id filter to duplicate detection query,
   passed org_id to get_candidate_applications(), update_candidate_from_resume(),
   sync_candidate_data_to_applications()
9. resume_upload_service.py — Passed org_id to get_candidate_applications()

Findings 11 and 18 (entity_service.py get_state/list_relations) were already
protected by entity ownership validation guard pattern — no code change needed.

PASS 2 (code guardian review): Fixed additional issues found during review.

Additional files modified (3):
10. documents.py (route) — Added org_id to list_entity_documents, get_document,
    delete_document, get_document_metadata, process_document routes. These routes
    had org_id available but were NOT passing it to service functions.
11. document_service.py — Added org_id param to get_document_stream() and pass
    through to get_document()
12. transition_service.py — Pass entity.organization_id to find_event_by_idempotency()
    in _idempotency_response()

Additional fixes in existing files:
- guard_service.py — Also added org_id filter to STAGE_COMMENT_REQUIRED guard
- events.py (route) — Pass org_id to list_events() service call

Total: 12 files modified, 22+ queries scoped to organization.

No migration required. All new params are Optional where callers may not have
org_id available (backward compatibility).
```

---

## SWARM-03: Transition Pop-up with Mandatory Comments and Fields

| | |
|---|---|
| **Wave** | **P1** |
| **Type** | Feature |
| **Reporter** | Shilpa Mishra, Vikas |
| **Migration** | None required (config stored in state machine JSON definition) |
| **Branch** | `feat/swarm-03-transition-dialog` |

### Description

When a recruiter clicks a transition button (e.g., "Move to Panel"), a pop-up should appear requiring comments, prime fields, and mandatory fields — instead of firing the transition directly.

### Grooming Decisions

- **Prime fields config:** Per-transition, stored in the funnel definition alongside `guards[]` and `require_comment`.
- **Related entity fields in dialog:** Yes — show editable fields from related entities (e.g., Candidate fields on Application transition). **CHECK: verify that editing reference fields actually updates the source entity and doesn't create a copy.**
- **HITL_REQUIRED handling:** Skip for now — not enough requirements clarity.
- **New guard type:** No — reuse existing `FIELD_PRESENT` guard with existing params.

### Acceptance Criteria

- [x] Clicking a transition button opens a **Transition Dialog** instead of firing immediately
- [x] Dialog shows: stage label, comment textarea (if `require_comment` configured), mandatory fields (from `FIELD_PRESENT` guards), and prime fields
- [x] Prime fields — configurable per-transition in funnel builder, surfaced at top of dialog even if not mandatory
- [x] Guard pre-check: `GET /preflight` fetches guard requirements before showing dialog
- [x] Dialog submit: fill fields + add comment + execute transition in one action
- [ ] If all guards already pass and no comment required, transition fires without dialog (fast path preserved) — _Dialog always opens; fast-path can be added by checking preflight.needs_dialog before opening_
- [ ] Related entity fields shown and editable in dialog — _Deferred: requires form schema resolution for reference fields; preflight returns field data from entity.data only_
- [x] Funnel builder UI: prime_fields config per transition

### System Design

```
User clicks "Move to Panel"
       ↓
[New] GET /entities/{id}/transitions/{trigger}/preflight
       → Returns: { required_fields[], prime_fields[], comment_config, guard_status[] }
       ↓
[New] TransitionDialog.tsx opens with:
       - Prime fields (editable, from transition config)
       - Mandatory fields (from FIELD_PRESENT guards)
       - Comment textarea (from require_comment config)
       - Related entity fields (from reference field config)
       ↓
User fills in fields + writes comment → Submit
       ↓
[Existing] PATCH entity (update fields) + POST comment + POST transition
```

**Backend:**
- NEW: `GET /transitions/{trigger}/preflight` endpoint in `transitions.py`
- NEW: `preflight_transition()` method in `transition_service.py` — evaluates guards without executing
- MODIFIED: Transition definition schema — add `prime_fields[]` config alongside `guards[]` and `require_comment`
- Reuse `FIELD_PRESENT` guard (no new guard type)

**Frontend:**
- NEW: `TransitionDialog.tsx` — modal with dynamic field rendering
- MODIFIED: `ApplicationDetailPanel.tsx` — transition buttons open dialog instead of firing directly
- MODIFIED: `FunnelBuilder/TransitionsStep.tsx` — add prime_fields config per transition

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| Guard evaluation | `guard_service.evaluate_guards()` | Pre-check which guards will fail |
| Comment requirements | `stage_comment_service.get_comment_requirements()` | Fetch comment config |
| FIELD_PRESENT guard | `guard_service.py:139-144` | Already checks entity.data[field] |
| STAGE_COMMENT_REQUIRED | `guard_service.py:200-230` | Already validates comments |
| Transition definition | State machine JSON `guards[]` and `require_comment` | Source of truth |
| Form schema | `FormSchema` | Field labels, types, options for dialog rendering |
| useAvailableTransitions | `frontend/src/domains/ats/hooks/` | Already fetches transitions with guard results |
| Funnel builder guards UI | `FunnelBuilder/TransitionsStep.tsx` | Guard config UI (for admin setup) |

### Agent Feedback

> Agent: agent2

**Started:** 7 Feb 2026
**Completed:** 7 Feb 2026
**Notes:**

```
Implementation complete. All acceptance criteria addressed:

BACKEND:
- Added PreflightResponse, PreflightFieldRequirement, PreflightCommentConfig schemas
  to backend/app/schemas/transition.py
- Added preflight_transition() method to backend/app/services/transition_service.py
  - Loads machine definition with fallback logic
  - Evaluates guards via dry run (no side effects)
  - Extracts required fields from FIELD_PRESENT guards
  - Extracts prime_fields from transition definition config
  - Checks comment requirements via stage_comment_service
  - Returns needs_dialog flag for fast-path optimization
- Added GET /entities/{id}/transitions/{trigger}/preflight endpoint
  to backend/app/api/routes/transitions.py

FRONTEND:
- Added PreflightResponse, PreflightFieldRequirement, PreflightCommentConfig types
  to frontend/src/core/types/index.ts
- Added transitions.preflight() API method to frontend/src/core/services/api.ts
- Created frontend/src/domains/ats/components/TransitionDialog.tsx
  - Calls preflight on open, renders required fields, prime fields, comment textarea
  - On submit: updates entity fields → adds comment → executes transition
  - Shows guard status and blocked reasons
  - Validates required fields and min comment length before submit
- Modified AvailableActionsSection.tsx
  - Transition buttons now open TransitionDialog instead of firing directly
  - Dialog handles full transition lifecycle (field update + comment + execute)
  - Added onUpdated prop — onTransitionComplete calls fetchData() + onUpdated()
    instead of re-executing via onTransition (fixed double-execution bug)
- Added FunnelPrimeFieldsConfig type to frontend/src/domains/ats/types/funnel.ts
- Added primeFields property to FunnelTransition type
- Modified FunnelBuilder/TransitionsStep.tsx
  - Transitions are now expandable (chevron toggle)
  - Expanded view shows prime fields config with field selector dropdown
  - Field selector fetches form schema via useFormSchema('ATS.Application')
  - Fields grouped into "Native Fields" and "Referenced Fields" with search filter
  - Selected fields show human-readable labels (not raw IDs)
  - Reference fields display source entity label and link icon
- Modified PipelineBoard.tsx
  - Kanban drag-and-drop now opens TransitionDialog instead of firing directly
  - Added pendingDragTransition state, TransitionDialog renders at page level
  - On dialog completion, refreshes board data via fetchData()
- Fixed prime_fields persistence in funnelConverter.ts
  - Save path: funnelToApiDefinition() now includes prime_fields in transition object
  - Load path: apiToFunnel() now extracts prime_fields from definition
  - Added prime_fields to FunnelApiResponse type in services/api.ts

BUGS FIXED:
- INVALID_STATE double-execution: TransitionDialog.handleSubmit executed the
  transition, then onTransitionComplete called onTransition() which called
  handleTransition() executing it again. Second call failed because entity
  had already moved states. Fixed by calling onUpdated() for data refresh
  instead of re-executing.
- Prime fields not persisting: funnelConverter.ts stripped prime_fields on save
  and didn't extract them on load. Fixed both directions.

TypeScript compiles clean (npx tsc --noEmit passes with no errors).
No migration needed — config stored in state machine JSON definition.
```

---

## SWARM-02: Email Forwarding to ATS

| | |
|---|---|
| **Wave** | **P1** |
| **Type** | Feature |
| **Reporter** | Vikas |
| **Migration** | `042_add_inbound_emails_table` |
| **Branch** | `feat/swarm-02-email-forward` |

### Description

Allow users to forward emails to the ATS. Email content and attachments are captured and linked to the relevant candidate/application. Phase 1 is auto-processing; UI triage deferred to Phase 2.

### Grooming Decisions

- **Email provider:** AWS SES inbound. Document all AWS infrastructure changes needed in deployment guide.
- **Linking to job/application:** Auto-match by sender email + UI triage step (Phase 2).
- **Web UI triage:** Auto-processing in Phase 1, manual triage UI deferred.
- **Rate limiting/spam:** Use engineering judgement. Reuse existing infrastructure.

### User Scenarios

1. **Resume via email** — Recruiter forwards a referral resume to ATS. System creates candidate and extracts data.
2. **Candidate correspondence** — Email thread with candidate forwarded to ATS, attached to application timeline.
3. **Agency submission** — Agency sends candidate profiles via email, recruiter forwards to import.

### Acceptance Criteria

- [ ] Dedicated inbound email address per organization (e.g., `intake-{org-slug}@ats.newtuple.com`)
- [ ] Parse email: extract sender, subject, body (HTML→text), and attachments
- [ ] If attachment is a resume (PDF), run through existing resume extraction pipeline
- [ ] If email matches existing candidate (by sender email), attach to their timeline
- [ ] If no match, create new candidate from email metadata
- [ ] Store email thread as `email_thread` document type on the entity
- [ ] AWS infrastructure changes documented in deployment guide

### System Design

```
Email sent to intake-{org}@ats.newtuple.com
       ↓
AWS SES Receiving Rule → stores raw email in S3
       ↓
SNS notification → backend webhook
       ↓
[New] POST /api/inbound-email/webhook
       ↓
[New] inbound_email_service.py — parse email (stdlib email + beautifulsoup4)
       ↓
Auto-match sender email → existing candidate?
   YES → attach to candidate timeline as email_thread document
   NO  → create new candidate from email metadata
       ↓
If PDF attachment → [Existing] resume_upload_service pipeline
```

**AWS Infrastructure Required** (document in deployment guide):
- SES domain verification for `ats.newtuple.com`
- SES receiving rule set: route to S3 bucket `ats-inbound-emails`
- SNS topic → HTTPS subscription to backend webhook
- S3 bucket with lifecycle policy (30-day retention)
- IAM role for SES → S3 → SNS

**Backend:**
- NEW: `inbound_email_service.py` — email parsing, sender matching, attachment routing
- NEW: `inbound_email.py` route — SES webhook endpoint
- NEW: Migration `042_add_inbound_emails_table` — tracking table for received emails
- MODIFIED: `email_config_service.py` — SES inbound configuration

**Frontend:** None in Phase 1.

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| Email config | `email_config_service.py` | SES/SMTP configuration |
| Document upload | `document_service.upload_document()` | Store as `email_thread` document |
| Resume extraction | `resume_upload_service.py` | Process PDF attachments |
| Entity creation | `entity_service.create_entity()` | Create candidates from email data |
| Document type: email_thread | `document_config_service.py` | Already defined with upload contexts |

### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** 2026-02-07
**Completed:** 2026-02-07
**Notes:**

```
Implemented inbound email pipeline: inbound_emails table + model, SNS webhook route, SES/S3 email parsing, candidate match/create, resume PDF processing, email_thread document attachment, env/config knobs, and SES deployment guidance. Added parsing tests.
```

---

## SWARM-05: Resume Upload Performance (Slow — ~2 min per resume)

| | |
|---|---|
| **Wave** | **P1** |
| **Type** | Bug / Performance |
| **Reporter** | Shilpa Mishra |
| **Migration** | None required |
| **Branch** | `feat/swarm-05-resume-perf` |

### Description

Uploading a single resume takes ~2 minutes. Target: under 15 seconds. Root cause is multi-turn LLM agent calls (3-4 iterations at 5-15s each).

### Grooming Decisions

- **Target time:** Under 15 seconds per resume.
- **Model switching:** Already configurable in UI — nothing to do here.
- **Fast mode toggle:** No — optimize the existing agent path instead.

### Current Architecture & Bottlenecks

| Stage | Location | Bottleneck |
|-------|----------|------------|
| 1. File upload | `resume_upload.py` → MinIO | Fast (~1-2s) |
| 2. PDF text extraction | `resume_parser_service.py` | Fast (~1-2s) |
| 3. **LLM/Agent extraction** | `DocumentAgentExecutor.extract_only()` | **Slow — 30-90s** |
| 4. Duplicate detection | `resume_upload.py:801-830` | Fast |
| 5. Result storage | DB write | Fast |

Stage 3 makes 3-4 LLM calls: `get_form_schema()` → `read_document()` → extract → `get_entity()`.

### Acceptance Criteria

- [ ] Resume extraction completes in under 15 seconds (measured end-to-end)
- [ ] Timing instrumentation logs added to each pipeline stage
- [ ] Form schema cached across batch extractions (schema doesn't change between resumes)
- [ ] Agent prompt restructured to reduce LLM round-trips from 3-4 to 1-2
- [ ] `MAX_CONCURRENT_EXTRACTIONS` increased from 4 to 8
- [ ] No regression in extraction accuracy

### System Design

```
CURRENT (3-4 LLM calls, ~60-90s):
  Agent → get_form_schema() → LLM → read_document() → LLM → extract → LLM → get_entity() → LLM

TARGET (1-2 LLM calls, <15s):
  Pre-inject schema + document text into system prompt → LLM → extract JSON
```

**Backend:**
- MODIFIED: `document_agent.py` — pre-inject cached `get_form_schema` result into system prompt
- MODIFIED: `prompts.py` — restructure system prompt to include schema inline
- MODIFIED: `resume_upload_service.py` — increase `MAX_CONCURRENT_EXTRACTIONS` from 4 to 8
- ADD: Timing instrumentation (log each stage duration)
- Cache form schema per `(entity_type, org_id)` across batch extractions

### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** Feb 7, 2026
**Completed:** _date_
**Benchmark before:** _X seconds per resume_
**Benchmark after:** _X seconds per resume_
**Notes:**

```
Work done by agent3:
- Implemented inline schema/text extraction to reduce agent tool calls
- Added per-stage timing logs
- Cached form schema per org/entity
- Raised concurrency to 8
Benchmarks pending.
```

---

## SWARM-04: Job Description Document Upload

| | |
|---|---|
| **Wave** | **P1** |
| **Type** | Feature |
| **Reporter** | Shilpa Mishra, Vikas |
| **Migration** | `043_add_jd_document_type` (data migration — adds JD doc type + agent to existing tenants) |
| **Branch** | `feat/swarm-04-jd-upload` |

### Description

Allow uploading a JD (PDF/DOCX/text) to a Job entity. System agent extracts requirements, skills, experience level, and responsibilities into Job fields. This is a system agent shipped to all tenants.

### Grooming Decisions

- **Extraction behavior:** Agent uses `update_entity` tool to populate job fields directly.
- **System agent:** JD extraction agent is system-defined, shipped to all tenants via provisioning + migration.
- **Job detail UI:** Dedicated "Job Description" section (not the generic Documents section).
- **Text paste:** Stores directly as a field on the Job entity (no document created).

### Acceptance Criteria

- [ ] New `jd` document type with upload context for `ATS.Job`
- [ ] Upload PDF, DOCX, or TXT job descriptions
- [ ] Agent-based extraction: parse JD to populate job entity fields via `update_entity`
- [ ] System agent `jd_extraction_agent` in DEFAULT_AGENTS, provisioned to all tenants
- [ ] Migration `043` adds JD doc type + agent to all existing tenants
- [ ] Dedicated "Job Description" section in Job detail view
- [ ] Text paste stores directly as `data.description` field on Job entity
- [ ] File upload goes through document upload pipeline with agent processing

### System Design

```
User opens Job detail → "Job Description" section
       ↓
Option A: Upload PDF/DOCX
       → [Existing] document_service.upload_document()
       → [Existing] DocumentAgentExecutor with JD-specific prompt
       → Agent calls update_entity to populate job fields
       ↓
Option B: Paste text
       → [Direct] PATCH entity data.description field
```

**Backend:**
- MODIFIED: `document_config_service.py` — add `jd` to `DEFAULT_DOCUMENT_TYPES` with `upload_contexts: [{"entity_type": "ATS.Job"}]`
- MODIFIED: `agent_definition_service.py` — add `jd_extraction_agent` to `DEFAULT_AGENTS`
- MODIFIED: `tenant_provisioning_service.py` — provision JD doc type + agent for new tenants
- NEW: Migration `043_add_jd_document_type` — data migration for existing tenants
- Agent prompt: extract `skills_required`, `experience_level`, `responsibilities`, `qualifications` → `update_entity` tool

**Frontend:**
- NEW: `JobDescriptionSection.tsx` — dedicated section in Job detail view
- Text paste: direct field update
- File upload: existing `EntityDocuments` upload flow

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| Document type config | `document_config_service.py` | Add new `jd` type |
| Document upload | `document_service.upload_document()` | Core upload + agent pipeline |
| Agent extraction | `DocumentAgentExecutor` | Configurable system prompts per doc type |
| EntityDocuments component | `frontend/src/core/components/EntityDocuments.tsx` | Upload UI based on upload_contexts |
| Form schema | Job form schema | Target fields for extracted JD data |

### Agent Feedback

> Agent: agent3

**Started:** 7 Feb 2026
**Completed:** 7 Feb 2026
**Notes:**

```
All acceptance criteria addressed. Changes made:

BACKEND:
1. document_config_service.py — Added JD_AGENT_SYSTEM_PROMPT, JD_AGENT_PROMPT,
   JD_AGENT_TOOLS constants. Added 'jd' entry to DEFAULT_DOCUMENT_TYPES with:
   - allowed_extensions: [".pdf", ".docx", ".txt"]
   - agent_enabled: True (uses DocumentAgentExecutor pipeline)
   - upload_contexts: [{"entity_type": "ATS.Job"}]
   - is_system: True
   - Agent extracts description, requirements, experience_level via update_entity tool

2. agent_definition_service.py — Added 'jd_extraction_agent' to DEFAULT_AGENTS with:
   - Tools: read_document, get_form_schema, get_entity, update_entity
   - max_iterations: 5, no approval required (automated)
   - is_system: True

3. tenant_provisioning_service.py — No changes needed. Already calls
   seed_default_document_types() and seed_default_agents() which are idempotent.
   New tenants automatically get JD doc type + agent from the updated defaults.

4. Migration 043_add_jd_document_type.py — Data migration that iterates all
   active organizations and inserts 'jd' document type config + 'jd_extraction_agent'
   agent definition. Idempotent (checks for existing before insert). Downgrade
   removes both.

FRONTEND:
5. JobDescriptionSection.tsx (NEW) — Dedicated section in Job detail view with:
   - Text paste: textarea to paste/edit description, saves directly to data.description
   - Edit mode: pre-populates with existing description for editing
   - File upload: reuses EntityDocuments component filtered to ATS.Job upload contexts
   - Shows current description in a styled card when not editing

6. JobDetail.tsx (MODIFIED) — Replaced generic "Job Documents" EntityDocuments
   with new JobDescriptionSection component. Import added.

BUGFIXES (post-implementation):
7. unified_executor.py — Added missing MCP tools (get_form_schema, search_entities,
   list_entity_types, get_picklist_values, list_document_types, send_calendar_invite)
   to ALL_TOOLS list. Was causing 400 error when saving JD agent definition.

8. Migration 043 updated — Added agent_system_prompt + agent_prompt to INSERT.
   Added backfill UPDATE for existing records missing prompts.
   document_config_service.py seed also backfills prompts on existing records.

9. document_service.py — Added flag_modified(entity, "data") to upload, delete,
   and update_extracted_data paths. Fixed SQLAlchemy JSON column mutation detection
   issue where documents weren't visible after delete + re-upload.

10. EditJobModal.tsx — Added description (textarea), requirements (textarea), and
    experience_level (select dropdown) to the Edit Job modal. Added entity data
    fetch in useEffect to populate fields from full entity. Updated submit handler
    to include new fields in PATCH payload.

GUARDS ENHANCEMENT:
11. funnel.ts — FIELD_PRESENT and POLICY_CHECK guard field param changed from
    hardcoded options to dynamic: 'entity_fields'. Fields now populated from
    ATS.Application form schema at runtime. Added GuardParamFieldOption type
    with optgroup support.

12. FunnelBuilder/index.tsx — Fetches ATS.Application form schema via
    useFormSchema hook. Builds grouped field options (Entity Fields vs Reference
    Fields) and passes to GuardsStep.

13. GuardsStep.tsx — Accepts fieldOptions + fieldsLoading props. Renders grouped
    <optgroup> selects for dynamic entity fields. Shows loading spinner while
    schema loads. Falls back to text input if no schema available.

14. RELATION_EXISTS guard — Marked as beta: true. Changed relation_type param
    from free-text to select with richOptions grouped by entity:
    - Candidate: APPLIED_TO, HAS_CANDIDATE
    - Job: JOB_APPLICATION, FOR_JOB
    Beta badge shown on guard card header and "Add Requirement" button.

DESIGN DECISIONS:
- Text paste saves directly to entity data.description (no document created) per spec
- File upload goes through existing document_service.upload_document() pipeline
  which triggers DocumentAgentExecutor with JD-specific prompts
- Agent uses update_entity tool to populate job fields, preserving existing
  title/department/location values
- JD doc type is system type (cannot be deleted by users)
- Guard field selectors are driven by form schema API, not hardcoded lists
- RELATION_EXISTS marked as beta — relation types are discoverable via dropdown

GUARD UX FIX:
15. AvailableActionsSection.tsx — Transition buttons no longer grayed out when
    guards fail. Removed cursor-not-allowed styling. Buttons always clickable,
    opening TransitionDialog where users can see requirements and fill in fields.
    Added amber "Requirements pending" badge next to transition label instead.

16. PipelineBoard.tsx — Drag-and-drop no longer blocks with alert() when guards
    are unmet. Blocked transitions are valid drop targets that open TransitionDialog.
    Column hover text changed from "Blocked" to "Drop to review requirements".
    Trigger lookup no longer filters by all_guards_passed so correct trigger is
    resolved for blocked transitions.

ROOT CAUSE: Guards were frontend-blocking interaction at two points (disabled
buttons + drag alert) before users could reach the TransitionDialog, which
already handles guard display and field collection correctly.
```

---

## SWARM-09: Backward Pipeline Movement

| | |
|---|---|
| **Wave** | **P2** (blocked by SWARM-03) |
| **Type** | Feature |
| **Reporter** | Team |
| **Migration** | `044_add_backward_transitions` (data migration — adds backward transitions to existing funnels) |
| **Branch** | `feat/swarm-09-backward-movement` |

### Description

Allow candidates to be moved backward in the hiring pipeline (e.g., REJECTED → SCREENING). The state machine engine already supports arbitrary `from → to` transitions — this is primarily a configuration and UI change.

### Grooming Decisions

- **Default backward transitions:** Any stage can go back to any earlier stage (option b).
- **Admin approval:** Not required — any recruiter can move candidates backward.
- **Loop prevention:** No hard limit on backward moves, but detect and prevent infinite loops (e.g., A→B→A→B).
- **Previous round content:** Mark comments/documents from previous passes with "From previous round".

### Acceptance Criteria

- [ ] Backward transitions defined in standard funnel (any stage → any earlier stage)
- [ ] All backward transitions have `STAGE_COMMENT_REQUIRED` guard (require explanation)
- [ ] Funnel builder UI allows selecting earlier stages as transition targets
- [ ] Loop detection: prevent direct back-and-forth cycles
- [ ] SLA timers reset when moving backward
- [ ] Previous round's comments/docs marked with `round: N` metadata
- [ ] "From previous round" badge in UI for previous-round content
- [ ] Migration `044` adds backward transitions to existing funnels
- [ ] Application timeline clearly shows backward movement

### System Design

```
Admin defines backward transitions in Funnel Builder:
  REJECTED → SCREENING (guard: STAGE_COMMENT_REQUIRED)
  PANEL → SCREENING (guard: STAGE_COMMENT_REQUIRED)
  ... (any stage → any earlier stage)
       ↓
Recruiter clicks backward transition → comment dialog → execute
       ↓
SLA timers reset for target stage
       ↓
Previous round's comments/docs marked with "round: N" metadata
       ↓
Loop detection: warn if entity has visited target state 3+ times (soft limit)
```

**Backend:**
- MODIFIED: `standard_funnel.py` — add backward transitions (any → any earlier) with `STAGE_COMMENT_REQUIRED`
- MODIFIED: `transition_service.py` — loop detection, round counter in entity metadata, SLA timer reset
- MODIFIED: `signal_service.py` — cancel active SLA timers on backward movement
- NEW: Migration `044_add_backward_transitions` — update existing funnels with backward transitions
- Mark previous-round content: add `round` field to comment/doc metadata

**Frontend:**
- MODIFIED: `FunnelBuilder/TransitionsStep.tsx` — allow earlier stages as targets
- MODIFIED: `ApplicationDetailPanel.tsx` — backward transition buttons (visually distinct)
- "From previous round" badge on comments/docs

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| State machine engine | `transition_service.py` | Already supports any from→to |
| Funnel builder | `FunnelBuilder/TransitionsStep.tsx` | Just needs backward targets enabled |
| Standard funnel | `defaults/standard_funnel.py` | Add default backward transitions |
| SLA signals | `Signal` model + signal service | Cancel/reschedule timers |
| Event log | `EntityEvent` | Transitions already logged |

### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** _date_
**Completed:** _date_
**Notes:**

```
```

---

## SWARM-07: Multiple Assignment Document Uploads + Links

| | |
|---|---|
| **Wave** | **P2** (blocked by SWARM-06) |
| **Type** | Bug / Feature |
| **Reporter** | Shilpa Mishra, Vikas |
| **Migration** | None required (links stored in entity.data JSON) |
| **Branch** | `feat/swarm-07-multi-assignments` |

### Description

Currently only 1 assignment document can be uploaded per application. Users need multiple assignment docs and external links (GitHub repos, Google Docs, portfolio URLs).

### Grooming Decisions

- **Links storage:** Separate `links[]` array in entity data (not a document subtype).
- **File limit:** Max 10 files per doc type per entity. Zip counts as 1 file.
- **Link metadata:** Support title and description alongside URL.

### Acceptance Criteria

- [ ] Upload N assignment documents to a single application (append, not replace)
- [ ] Attach external links with metadata `{url, title, description}`
- [ ] Display all assignment docs and links in application detail view
- [ ] Delete individual assignment docs or links without affecting others
- [ ] Max 10 files per doc type per entity (zip = 1 file)
- [ ] Fix: verify and remove `replace_type` behavior for assignment uploads

### System Design

```
Application entity.data:
{
  "documents": [...],          ← existing, fix to allow multiple per type
  "links": [                   ← NEW
    { "url": "https://...", "title": "GitHub Repo", "description": "Assignment code" },
    { "url": "https://...", "title": "Portfolio", "description": "" }
  ]
}
```

**Backend:**
- MODIFIED: `document_service.py` — remove `replace_type` for assignment uploads (append instead)
- NEW: `POST /entities/{id}/links` — add link with metadata `{url, title, description}`
- NEW: `DELETE /entities/{id}/links/{index}` — remove a link
- Enforce max 10 files per doc type per entity

**Frontend:**
- MODIFIED: `EntityDocuments.tsx` — allow re-upload for same doc type (don't disable after first)
- NEW: "Add Link" button + link list display in assignment section
- MODIFIED: `ApplicationDetailPanel.tsx` — render links alongside documents

### Investigation Required

- [ ] Check if assignment upload path uses `replace_type` (which overwrites instead of appending)
- [ ] Verify frontend allows re-uploading same doc type (may disable button after first upload)

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| Document upload | `document_service.upload_document()` | Appends if `replace_type` not set |
| EntityDocuments | `frontend/src/core/components/EntityDocuments.tsx` | Renders document lists |
| Document metadata | `DocumentMetadata` schema | Could extend for link data |

### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** _date_
**Completed:** _date_
**Notes:**

```
```

---

## SWARM-01: CSV/Excel Bulk Candidate Import

| | |
|---|---|
| **Wave** | **P2** (blocked by SWARM-04, SWARM-06) |
| **Type** | Feature |
| **Reporter** | Shilpa Mishra, Vikas |
| **Migration** | `045_add_csv_import_agent` (data migration — adds spreadsheet doc type + system agent to existing tenants) |
| **Branch** | `feat/swarm-01-csv-import` |

### Description

Enable direct upload of Excel/CSV sheets to bulk-create or upsert candidates and applications. Processed by a system agent using the existing agent framework.

### Grooming Decisions

- **Column mapping:** Agent-based — the spreadsheet is processed by a system agent (not manual column mapping UI). Agent uses form schema to map columns.
- **Limits:** 100 rows max, 10 MB max file size.
- **Upsert:** Yes — upsert by email address.
- **Entity types:** Candidates and Applications. Reuse existing agent framework.

### User Scenarios

1. **Placement agency handoff** — Agency sends spreadsheet of 5 candidates. Recruiter uploads, all 5 appear in system.
2. **Job board export** — CSV downloaded from Naukri imported directly.
3. **Manual LinkedIn research** — Recruiter builds spreadsheet of 12 profiles, imports in one go.

### Acceptance Criteria

- [ ] Upload `.xlsx`, `.xls`, and `.csv` files via dedicated import UI
- [ ] System agent parses spreadsheet, maps columns to form schema, creates/upserts candidates
- [ ] Upsert by email within user's organization
- [ ] Optionally link imported candidates to a selected job (creating applications)
- [ ] Import report: created, updated, skipped (duplicate), failed rows
- [ ] Limits: 100 rows, 10 MB max
- [ ] System agent `csv_import_agent` provisioned to all tenants
- [ ] Migration `045` adds spreadsheet doc type + agent to existing tenants
- [ ] Organization scoping on all created entities

### System Design

```
User uploads .xlsx/.csv
       ↓
[New] POST /api/import/candidates
       ↓
[New] csv_import_service.py — parse file (openpyxl / csv stdlib)
       ↓
[Existing] System agent "csv_import_agent" — validate rows, map columns to form schema
       ↓
[Existing] entity_service.create_entity() or update — per row (upsert by email)
       ↓
[Existing] UploadProgressPanel pattern — show created/updated/skipped/failed
```

**Backend:**
- NEW: `csv_import_service.py` — file parsing, row validation, batch create/upsert
- NEW: System agent `csv_import_agent` in `DEFAULT_AGENTS` (tenant provisioning)
- NEW: MCP tools: `parse_spreadsheet_row`, `upsert_candidate`
- NEW: Route `POST /api/import/candidates`
- NEW: `spreadsheet` document type in `DEFAULT_DOCUMENT_TYPES`
- NEW: Migration `045_add_csv_import_agent`
- MODIFIED: `tenant_provisioning_service.py`, `agent_definition_service.py`, `document_config_service.py`, `mcp_server.py`
- NEW dep: `openpyxl` in `requirements.txt`

**Frontend:**
- NEW: `ImportCandidatesDialog.tsx` — file upload + progress + results
- MODIFIED: Candidates page header — add "Import" button

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| Entity creation | `entity_service.create_entity()` | Core candidate creation |
| Resume upload job tracking | `ResumeExtractionJob`, `JobsContext` frontend | Progress pattern |
| Duplicate detection | `resume_upload.py:801-830` | Email-based matching (after SWARM-06 fix) |
| Form schema | `FormSchema` / `get_form_schema` | Field definitions for column mapping |
| Bulk transitions | `bulk.py` routes | Batch entity operations pattern |
| UploadProgressPanel | `frontend/src/components/UploadProgressPanel.tsx` | Progress UI |

### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** _date_
**Completed:** _date_
**Notes:**

```
```

---

## SWARM-08: Rejection Email (User-Approved)

| | |
|---|---|
| **Wave** | **P3** (blocked by SWARM-09) |
| **Type** | Feature |
| **Reporter** | Team |
| **Migration** | `046_add_email_templates` (DDL — creates `email_templates` table) |
| **Branch** | `feat/swarm-08-rejection-email` |

### Description

When a candidate is in the REJECTED state, a recruiter can send a rejection email with explicit approval. No automatic emails — always user-triggered with preview and confirmation. Requires a new email template admin subsystem.

> **Note:** User suggested grooming this ticket separately given the scope of the email template subsystem. Consider splitting into: (a) SWARM-08a: Email Template Admin, (b) SWARM-08b: Rejection Email Trigger.

### Grooming Decisions

- **Sending behavior:** NEVER automatic. Always requires explicit user approval — "Send Rejection Email" button with preview dialog.
- **Email templates:** Separate admin section in Settings with merge fields. Potentially groom as its own ticket.
- **Cancel on backward move:** Yes — if candidate moved back from REJECTED, cancel any pending email.
- **Candidate opt-out:** Yes — unsubscribe link in emails.

### Acceptance Criteria

- [ ] "Send Rejection Email" button on REJECTED applications (user-triggered only)
- [ ] Preview dialog with rendered template + merge fields before sending
- [ ] Email template admin section in Settings (CRUD for templates)
- [ ] Templates support merge fields: `{candidate_name}`, `{job_title}`, `{company_name}`, `{rejection_reason}`
- [ ] Cancel pending email if candidate moved backward from REJECTED (SWARM-09)
- [ ] Unsubscribe link support
- [ ] Audit log entry for each email sent
- [ ] Migration `046` creates `email_templates` table

### System Design

```
Candidate moved to REJECTED
       ↓
"Send Rejection Email" button appears on application detail
       ↓
User clicks → Preview dialog with template + merge fields rendered
       ↓
User confirms → email sent via email_service
       ↓
Audit log entry created
```

**Backend:**
- NEW: `email_template_service.py` — CRUD for templates with merge fields
- NEW: `email_templates` table — `{id, org_id, name, subject, body, merge_fields[], is_system}`
- NEW: `email_templates.py` route — admin CRUD endpoints
- NEW: `POST /entities/{id}/send-email` — send with template + merge data
- NEW: Migration `046_add_email_templates`
- MODIFIED: `transition_service.py` — on backward movement from REJECTED, cancel pending email (SWARM-09 dep)
- Merge fields: `{candidate_name}`, `{job_title}`, `{company_name}`, `{rejection_reason}`
- Unsubscribe link support

**Frontend:**
- NEW: `EmailTemplatesTab.tsx` — admin section in Settings
- NEW: Template editor with merge field insertion buttons
- MODIFIED: `ApplicationDetailPanel.tsx` — "Send Rejection Email" button on REJECTED apps
- NEW: Email preview/confirm dialog before sending

### Existing Modules to Reuse

| Module | Location | Reuse |
|--------|----------|-------|
| Email service | `email_service.py` | Send via SES/SMTP |
| Email handler | `tools/handlers/email_handler.py` | Send logic |
| Transition side effects | `transition_service.py:408-422` | Hook for post-transition actions |
| Signal/timer system | `Signal` model | Schedule delayed actions |
| Notification service | `notification_service.py` | Pattern for system emails |
| Entity relations | `EntityRelation` | Resolve Application → Candidate for email |

### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** _date_
**Completed:** _date_
**Notes:**

```
```

---

## Migration Number Registry

Reserved migration slots for this development cycle:

| Migration | Ticket | Type | Description |
|-----------|--------|------|-------------|
| `042` | SWARM-02 | DDL | `inbound_emails` tracking table |
| `043` | SWARM-04 | Data | Add JD doc type + `jd_extraction_agent` to existing tenants |
| `044` | SWARM-09 | Data | Add backward transitions to existing funnels |
| `045` | SWARM-01 | Data | Add spreadsheet doc type + `csv_import_agent` to existing tenants |
| `046` | SWARM-08 | DDL | Create `email_templates` table |

Tickets with no migration: SWARM-03, SWARM-05, SWARM-06, SWARM-07.
