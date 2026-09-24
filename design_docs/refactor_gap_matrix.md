# Refactor Gap Matrix (ats_newstart2 -> modular backend)

This matrix summarizes missing/partial backend features in `origin/feature/backend-refactoring` relative to `ats_newstart2`.

## Legend
- **Status**: `missing`, `partial`, `covered`
- **Priority**: `P0` (top), `P1`, `P2`
- **Target Module**: `core` (generalized state-machine backend) or `ats-skin`

## Gaps (Top Priority First)
| Feature / Route Group | Target Module (core vs ats-skin) | Proposed Modular Module | Status | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| Tasks (`/tasks`, `/entities/{entity_id}/tasks`) | core | `tasks` | covered | **P0** | Module implemented with DB-backed persistence and side-effect creation; workflow wiring pending elsewhere. |
| State machines & transitions (`/state-machines`, `/transitions`, `/signals`, `/events`, `/interventions`) | core | `workflow` | partial | P1 | Foundation added: state-machine CRUD/activate + available/preflight transition introspection; execution/events/signals/interventions remain. |
| Entities CRUD & state transitions (`/entities/{entity_id}/*`) | core | `workflow` + `entities` | partial | P1 | Modular `entities` only covers metadata registry today. |
| Roles & RBAC (`/roles`, `/resource-scopes`) | core | `identity_access` | missing | P1 | Needed for generalized permissions. |
| Users & organizations (`/users`, `/organizations/*`) | core | `organizations` + `identity_access` | partial | P1 | Modular has status only. |
| Invitations (`/invitations/*`) | ats-skin | `identity_access` + `organizations` | missing | P2 | ATS onboarding flow. |
| Notifications list/mark-read (`/notifications/*`) | core | `communications` | partial | P2 | Modular has create only. |
| Candidate/job/resume flows (`/candidates`, `/jobs`, `/resumes`) | ats-skin | `candidate_intake` + `documents` | missing | P2 | ATS-specific. |
| Scheduling (`/scheduling/*`) | ats-skin | `integrations_calendar` | missing | P2 | ATS scheduling flows. |
| Agent runtime (`/agent`, `/agent-traces`) | core | `agent_ai` + `agents` | partial | P2 | Modular has status only. |
| Config endpoints (`/config/*`) | core + ats-skin | `metadata_registry` + `llm` + `communications` | missing | P2 | AI config, picklists, funnel validation, etc. |
| Downloads / Chrome extension (`/downloads/*`) | ats-skin | `ats-skin` | missing | P3 | UI distribution only. |
| Bulk endpoints (`/bulk/*`) | core | `workflow` | missing | P3 | Batch transitions/states. |

## Coverage Notes (Existing Modular)
- `documents`, `communications`, `annotations`, `integrations`, `views/projections` are **partial** and use in-memory persistence.
- `auth` exists but lacks login/oauth/refresh flows and persistent user store.
- `entities` in modular is currently **metadata registry**, not entity lifecycle CRUD.
