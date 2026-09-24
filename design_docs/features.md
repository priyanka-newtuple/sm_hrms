# Newtuple ATS Platform — Feature Tracker

> Last updated: 2026-05-18  
> Version: 0.17.0

---

## Core State Machine Runtime

| Feature | Status | Notes |
|---------|--------|-------|
| State machine JSON DSL (states, transitions, guards, SLA) | ✅ Complete | `backend/workflow/` |
| Guard engine (`FIELD_PRESENT`, `RELATION_EXISTS`, `POLICY_CHECK`, `EXTERNAL_CHECK`, `HITL_REQUIRED`) | ✅ Complete | `backend/executor/` |
| Transition executor — atomic, idempotent, optimistic-locked | ✅ Complete | `state_version` column |
| Signals — SLA timeouts and timer-based automations | ✅ Complete | |
| Interventions (HITL) — manual approval blocks with override | ✅ Complete | |
| State machine versioning and publish/draft lifecycle | ✅ Complete | |
| Workflow path analysis | ✅ Complete | `POST /workflow-state-machines/workflow-paths` |

---

## Playbook / Automation Runtime

| Feature | Status | Notes |
|---------|--------|-------|
| Versioned playbook definitions | ✅ Complete | |
| Run orchestration (start / pause / resume / cancel) | ✅ Complete | |
| Step type: `AGENT_CALL` | ✅ Complete | |
| Step type: `TOOL_CALL` | ✅ Complete | |
| Step type: `ENTITY_TRANSITION` | ✅ Complete | |
| Step type: `WAIT` | ✅ Complete | |
| Step type: `HITL_WAIT` | 🟡 Partial | Defined; not integrated into playbook loop |
| Step type: `TIMER_WAIT` | 🟡 Partial | Defined; not integrated into playbook loop |
| Conditional branching | ❌ Not started | |
| Output aggregation across steps | ✅ Complete | |

---

## AI Agent Executor

| Feature | Status | Notes |
|---------|--------|-------|
| Agentic loop with configurable max iterations | ✅ Complete | Default 10 |
| MCP (Model Context Protocol) tool server | ✅ Complete | |
| LiteLLM multi-provider support (Anthropic, OpenAI, Ollama, custom) | ✅ Complete | `backend/llm/` |
| Per-org LLM config and API key management | ✅ Complete | `backend/llm_config/` |
| Agent definitions (system prompt, instructions, model) | ✅ Complete | |
| Agent sessions and chat history | ✅ Complete | |
| Agent execution traces | ✅ Complete | |
| Human-in-the-loop approval for agent actions | ✅ Complete | |
| Template variable substitution | ✅ Complete | |
| Tool access: entity CRUD, transitions, relations, interventions, signals, calendar, documents | ✅ Complete | |

---

## Entity & Data Management

| Feature | Status | Notes |
|---------|--------|-------|
| Generic entity runtime with JSONB data storage | ✅ Complete | Schema-flexible |
| Entity type registry with schema definitions | ✅ Complete | |
| Entity type relations (allowed directed edges) | ✅ Complete | |
| Directed graph relations between entities | ✅ Complete | |
| Append-only event timeline per entity | ✅ Complete | |
| Projections — denormalized pipeline view | ✅ Complete | |
| Projections — SLA heatmap | ✅ Complete | |
| Pipeline funnel aggregation statistics | ✅ Complete | |
| Three-schema DB design (definitions / runtime / audit) | ✅ Complete | |
| Async event consumers for projection updates | ❌ Not started | Currently synchronous; scalability gap |

---

## Document Processing Pipeline

| Feature | Status | Notes |
|---------|--------|-------|
| PDF text extraction and layout parsing | ✅ Complete | |
| Image OCR (Tesseract / Cloud Vision) | ✅ Complete | |
| Spreadsheet parsing (XLSX, CSV) | ✅ Complete | |
| Document classification | ✅ Complete | |
| LLM-based structured field extraction | ✅ Complete | Per-org configurable prompts |
| Processing job queue with retry | ✅ Complete | |
| Supported formats: PDF, DOCX, TXT, CSV, XLSX, PNG, JPG, GIF, WEBP | ✅ Complete | |
| Document annotations and highlighting | ✅ Complete | `backend/annotations/` |

---

## Authentication & Authorization

| Feature | Status | Notes |
|---------|--------|-------|
| Email / password auth with JWT | ✅ Complete | |
| Google OAuth 2.0 | ✅ Complete | |
| Microsoft OAuth 2.0 | ✅ Complete | |
| JWT refresh tokens | ✅ Complete | |
| Password reset flow | ✅ Complete | |
| RBAC (superadmin, admin, recruiter, user, viewer) | ✅ Complete | |
| Per-role permission model | ✅ Complete | |
| Multi-tenant org isolation (org_id DB-level scoping) | ✅ Complete | |
| User invitation workflow | ✅ Complete | |
| Organization membership management | ✅ Complete | |
| Auth audit log (login / logout / failure) | ✅ Complete | |

---

## Third-Party Integrations

| Integration | Status | Notes |
|-------------|--------|-------|
| Google Calendar — OAuth 2.0, event scheduling, availability queries | ✅ Complete | Tokens Fernet-encrypted |
| Google Calendar — ICS email fallback | ✅ Complete | |
| Email — SMTP | ✅ Complete | Per-org config |
| Email — AWS SES | ✅ Complete | |
| Azure Communication Services | ❌ Reverted | PR #f56de7d reverted in 5bf269a |
| Transcription (audio-to-text) | 🟡 Partial | Backend exists; UI not wired |

---

## Frontend Pages

| Page | Route | Status | Notes |
|------|-------|--------|-------|
| Pipeline Kanban Board | `/pipeline/:id` | ✅ Complete | Drag-drop, SLA badges, slide-over detail |
| Records listing | `/records` | ✅ Complete | Table/grid views, search, filters |
| Record detail | `/records/:entityType` | ✅ Complete | Form editor, bulk actions |
| Funnel Builder — Wizard mode | `/funnel/create` | ✅ Complete | Step-by-step builder |
| Funnel Builder — Canvas mode | `/funnel/create` | ✅ Complete | React Flow visual editor |
| Funnel edit | `/funnel/:id/edit` | ✅ Complete | |
| Settings hub | `/settings` | ✅ Complete | 12+ admin tabs |
| Login / SSO callbacks | `/login` etc. | ✅ Complete | |
| Forgot / reset password | `/forgot-password` | ✅ Complete | |
| Accept invite | `/accept-invite` | ✅ Complete | |
| Dashboard | `/dashboard` | 🟡 Partial | Shell only; metrics not wired |
| What's New | `/whats-new` | ✅ Complete | In-app changelog |

---

## Frontend Settings Tabs

| Tab | Status |
|-----|--------|
| Organizations | ✅ Complete |
| Users & invitations | ✅ Complete |
| Roles & permissions | ✅ Complete |
| Entity types + schema builder | ✅ Complete |
| Document types | ✅ Complete |
| Form schemas | ✅ Complete |
| Agents | ✅ Complete |
| Agent traces | ✅ Complete |
| Playbooks | 🟡 Partial | View only; editing UI not complete |
| Funnels / workflows | ✅ Complete |
| Integrations | ✅ Complete |
| Processing jobs | ✅ Complete |

---

## API Coverage

| Module | Endpoints | Status |
|--------|-----------|--------|
| Workflow state machines | CRUD, validate, publish, draft, paths | ✅ Complete |
| Entities | CRUD, state, transitions, events, relations | ✅ Complete |
| Entity types | CRUD, archive, toggle, relations | ✅ Complete |
| Agents | Definitions CRUD, chat, approve/reject, sessions, traces | ✅ Complete |
| Tools | Catalog, presets, execute, logs | ✅ Complete |
| Forms | CRUD, entity schema linking | ✅ Complete |
| Documents | CRUD, content retrieval | ✅ Complete |
| File processor | Jobs, retry, results, formats | ✅ Complete |
| File handler | Upload, download, delete | ✅ Complete |
| Communications / notifications | CRUD, mark read, email config | ✅ Complete |
| Playbooks | Status (full CRUD not yet routed) | 🟡 Partial |
| Tasks | CRUD | ✅ Complete |
| Auth | Register, login, refresh, logout, SSO | ✅ Complete |
| Users | Profile CRUD | ✅ Complete |
| Roles | CRUD | ✅ Complete |
| Organizations | CRUD | ✅ Complete |
| Invitations | Send, list, accept | ✅ Complete |
| Integrations | Google Calendar OAuth + events | ✅ Complete |
| Projections | Pipeline, heatmap, funnels | ✅ Complete |
| Scheduling | Interview scheduling | ✅ Complete |
| Health | Health check, readiness | ✅ Complete |
| LLM config | Provider CRUD | ✅ Complete |
| Signals | Management | ✅ Complete |
| Interventions | HITL workflow | ✅ Complete |

---

## Database

| Area | Status | Notes |
|------|--------|-------|
| PostgreSQL schema (3 schemas: definitions, runtime, audit) | ✅ Complete | |
| 17 Alembic migrations | ✅ Complete | Head: `2026_05_13_0001` |
| Optimistic locking (`state_version`) | ✅ Complete | |
| JSONB for flexible entity data | ✅ Complete | |
| Org-scoped composite FKs for multi-tenancy | ✅ Complete | |
| Indexes on org_id, entity_id, workflow_id | ✅ Complete | |

---

## Known Gaps / Backlog

| Item | Priority | Notes |
|------|----------|-------|
| Async event consumers for projections | High | Currently synchronous; needed for scale |
| `HITL_WAIT` playbook step integration | Medium | Backend defined; not wired into loop |
| `TIMER_WAIT` playbook step integration | Medium | Backend defined; not wired into loop |
| Dashboard metrics wiring | Medium | UI shell exists |
| Playbook editing UI | Medium | Backend complete |
| Intervention / Signal CRUD UI | Low | Backend complete |
| Conditional branching in playbooks | Low | |
| Bulk operations UI | Low | API exists |
| Azure Communication Services | — | Reverted; revisit if needed |
