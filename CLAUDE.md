# Guidance for Claude Code (claude.ai/code) working in this repository.Project Overview

Newtuple State Machine Platform — a generic, multi-tenant workflow/state-machine runtime that powers cockpit-style products (ATS first, PMO next). Split:

- **Platform core**: entities, workflow definitions + transitions, guards, forms, actions, tasks, views, agents, RBAC, audit
- **Domain/skin layer**: per-product entity types, workflows and UI skins configured per tenant (ATS.Job, ATS.Candidate, ATS.Application)

Most product behaviour is **configuration, not code**: entity types, forms, workflow states/transitions, views and dashboards are seeded per organization and edited in-app (Funnel Builder, Settings).

## Git Branching Strategy

`main` is the production branch and the repo default.

- **NEVER commit directly to** `main`
- Work on a feature branch: `feat/STAT-<id>-<slug>`, `fix/<slug>`, `perf/<slug>`
- Merge to `main` only via pull request or explicit user request
- Deploy from `main`



## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + Pydantic v2, Python 3.12+, uv-managed venv at `backend/.venv`
- **Frontend**: React 19 + TypeScript + Vite + Tailwind v4, TanStack Query, Zustand, MDX
- **Database**: PostgreSQL (Docker, host port **5455**), app schema `modular_backend`, Alembic migrations
- **Tooling**: ruff (lint + format) + pre-commit for backend, pyright (`pyrightconfig.json`), ESLint + `tsc -b` for frontend, Playwright for e2e



## Common Commands

Use the `Makefile` — it owns ports, env and the uv/nvm plumbing.

```bash
make install          # backend (uv) + frontend (npm) deps
make dev              # Postgres + backend (:8001) + frontend (:5173)
make backend          # Postgres + FastAPI on :8001, docs at /docs
make frontend         # Vite dev server on :5173 (proxies /api → 127.0.0.1:8001)
make db / make db-stop

make lint / lint-fix / format      # ruff, run from backend/
make precommit-install             # one-time git hook

make docker-up        # full stack: db :5455, backend :8001, frontend :5111
make docker-down / docker-logs / docker-ps
make migrate-db       # alembic upgrade head inside the backend container
make docker-db-shell  # psql into statemachine db
```

Migrations outside Docker: `cd backend && uv run alembic -c alembic.ini upgrade head`.

Config lives in `backend/etc/.env` (template `backend/etc/.env.example`); Docker Compose reads root `.env` (`make setup-env`). See README for the full env var list.

## Backend Architecture

Modules live **directly under** `backend/` (`entities/`, `workflow/`, `forms/`, `actions/`, `agent/`, `roles/`, `views/`, `documents/`, `tasks/`, …). Each is self-contained and follows a strict layering:

```
<module>/
  controller.py     # FastAPI routes only (class-based <Module>RestController)
  manager.py        # business orchestration (<Module>ServiceManager) — no FastAPI imports
  db_models.py      # persistence adapter (<Module>ModelService, SQLAlchemy) — no FastAPI imports
  models/
    request.py      # Pydantic request contracts
    response.py     # Pydantic response contracts
    interface.py    # cross-module contracts, enums, Protocols
```

Rules: controllers never import `db_models` directly; managers/db_models never import FastAPI. Enforced by `backend/tests/test_architecture_constraints.py`. Full conventions: `backend/README.md` and the `backend-codestructure` skill.

`backend/main.py` **is the composition root** — it builds every model service, service manager and controller and wires cross-module dependencies. Ordering matters: forms before entities/workflow; `WorkflowServiceManager` receives the entities and forms services; background-jobs and forms managers are back-linked to workflow after construction.

Shared infrastructure: `common/` (config, auth helpers, logger, enums, encryption), `database/` (engine/session/Base), `bootstrap/` (schema creation, migration run, per-tenant seed data), `alembic/` (migrations, naming + rules in `backend/alembic/versions/migration_guidelines.MD`).

**Multi-tenancy is the top correctness concern**: every query touching tenant data must filter by `organization_id`. Missing `org_id` filters are treated as security bugs (P1).

## Frontend Architecture

`frontend/src/`:

- `core/` — cross-product foundation: `services/` (API client), `stores/` (Zustand), `contexts/`, `hooks/`, `theme/`, `componentRegistry/`, `queryClient.ts`
- `pages/` — routed screens (`Pipeline`, `Workflows`, `records`, `funnel`, `dashboard`, `settings`, `agent`, `bulk-import`, `auth`, `Changelogs`, `publicform`)
- `domains/` — domain-specific config/types (e.g. `domains/ats`)
- `features/` — feature slices (e.g. `dashboard`)
- `shared/` + `components/` — reusable UI, hooks, types
- `skins/` — per-customer skin registry/config (`CUSTOMER_SKINS_PATH` can point at private skins)
- `layouts/` — app shell

Conventions: TanStack Query for server data, Zustand for client state, Tailwind v4 `@theme` tokens in `index.css`, Lucide icons, design language in `design_docs/styleguide.MD`. See the `frontend-codestructure`, `frontend-react` and `react-query` skills.

## Testing

- **Backend**: pytest in `backend/tests/` (module suites plus `test_architecture_constraints.py`). Requires the dev deps (`make install-backend`) and a running Postgres; tests default to `postgresql://statemachine:statemachine@modular-db:5432/statemachine` and honour `DATABASE_URL` / `POSTGRES_APP_SCHEMA`. Locally: `cd backend && DATABASE_URL=postgresql://statemachine:statemachine@localhost:5455/statemachine uv run pytest tests/ -q`, or run inside the container via `make docker-backend-shell`.
- **Frontend**: `npm run build` (type check) and `npm run test:e2e` (Playwright).



## Changelogs (What's New)

`/changelogs` renders MDX from the repo-root `changelogs/` directory — add a `YYYY-MM-DD-slug.mdx` file with the required frontmatter and it appears; no registry. Rules in `changelogs/README.md`. Page is hidden per org via the `hideWhatsNew` feature flag (Settings → Display).

Changelog entries are the live release record. `VERSION`, `RELEASES.md` and `frontend/package.json` still read `0.17.0` and are no longer updated per release — don't treat them as current unless the user asks to resume formal versioning.

## Wave Planning Agent

When asked for "wave planning", "sprint grooming", "swarm development", or to plan a batch of features/bugs for parallel development, follow `design_docs/wave_planning_playbook.md`.

Phases: 1) requirement intake → 2) codebase analysis → 3) grooming interview (2–4 questions per ticket) → 4) targeted audit (multi-tenancy/auth/data access) → 5) system design per ticket → 6) dependency analysis + wave assignment → 7) document assembly.

Key rules:

- **Maximize parallelism** — find the largest set of tickets that can run simultaneously
- **File conflicts determine waves** — two tickets touching the same file cannot share a wave
- **Migrations**: check the current Alembic head, then name new revisions per `backend/alembic/versions/migration_guidelines.MD` (`YYYY_MM_DD_NNNN_<slug>.py`), ordered by wave
- **Every ticket gets an Agent Feedback section** (started/completed dates + notes)
- **Security tickets are always P1**
- Output to `design_docs/`, named by session (e.g. `swarm_development_7Feb.MD`)



## Key Documents

- `REPO_MAP.md` — detailed repo/module map
- `README.md` — setup, env vars, make targets
- `backend/README.md` — module layering contract
- `design_docs/state_machine.MD` — core workflow architecture
- `design_docs/coding_guidelines.MD` — code conventions
- `design_docs/styleguide.MD` — Newtuple Design Language
- `backend/agent_guidelines/` — per-module notes for agent-driven work

