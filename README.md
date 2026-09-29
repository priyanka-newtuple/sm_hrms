# Newtuple State Machine Platform

A generic state machine workflow runtime designed to power multiple "cockpits" (ATS first, PMO next). The architecture separates a platform core (state machine engine, event audit, guards, interventions, signals) from domain packs (application-specific entities, workflows, and integrations).

## HRMS local preview

With Docker Desktop running, start the isolated HRMS stack from this repository:

```powershell
powershell -NoProfile -File scripts/hrms-local.ps1 up
```

Open [http://localhost:5181](http://localhost:5181) and choose a seeded role on the login page. The HRMS API is on `http://localhost:8011`; its database is on loopback port `5456`. This Compose project uses its own images and volumes and does not connect to the legacy HRMS database. The generated `.hrms.local.env` contains local secrets and is ignored by Git.

```powershell
powershell -NoProfile -File scripts/hrms-local.ps1 test
powershell -NoProfile -File scripts/hrms-local.ps1 logs
powershell -NoProfile -File scripts/hrms-local.ps1 down
```

The test command uses only the disposable `sm_hrms_test` database. See [the migration plan](design_docs/hrms_migration_plan.md) for the compatibility boundary and production gates.

To inspect the native state-machine backend being prepared for HRMS, run:

```powershell
powershell -NoProfile -File scripts/hrms-local.ps1 native-up
```

This starts the HRMS application at [http://localhost:5182](http://localhost:5182). Its separate API layer (`applications/hrms_api`) is on loopback port 8012 and calls the unchanged platform through its public APIs. The core API is internal to Docker. The application database holds retry checkpoints and actor audit entries; HR records and workflow state remain in the platform database.

Sign in as `hrms-admin@newtuple.com` using `HRMS_PLATFORM_ADMIN_PASSWORD` from the ignored `.hrms.local.env`. Open Employees to add a hire, Onboarding to see all steps and complete permitted actions, or Quick actions to see ready work. Employee creation also creates a pending identity, a native onboarding case, and eight native step entities. Identity activation and invitation delivery are separate; this refactor does not send invitations.

Copy the local administrator password without printing it (run from this repository):

```powershell
(Get-Content .hrms.local.env | Where-Object { $_ -like 'HRMS_PLATFORM_ADMIN_PASSWORD=*' }).Split('=', 2)[1] | Set-Clipboard
```

Existing local employee/manager credentials and role assignments are preserved. The bootstrap administrator is not an employee and cannot submit personal leave without a linked employee profile. The role policy is application-owned configuration, with backend authorization on every action.

```powershell
# Existing pre-refactor onboarding tasks: read-only export, API-only target writes
powershell -NoProfile -File scripts/hrms-local.ps1 native-migrate-steps
# Integration check on the existing imported local demo stack; retains named fixtures
powershell -NoProfile -File scripts/hrms-local.ps1 native-test
# Verify tracked platform sources still match the original baseline
python scripts/verify-platform-boundary.py
```

The old `native-import`, `native-identities`, `native-demo`, and `native-reconcile` commands were retired because they imported platform internals or wrote platform tables. Existing imported records remain in place. A general legacy import/activation tool using only public APIs remains future migration work.

See [the application-layer architecture](design_docs/hrms_application_layer.md) for the API boundary, deployment model, verification, and limitations. Other legacy modules remain in the separate compatibility preview on port 5181; full feature parity is still in progress.

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + Pydantic + PostgreSQL
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS
- **Python**: 3.13
- **Database**: PostgreSQL 16 (via Docker)

## Quick Start (Local Development)

### Prerequisites

- Python 3.13+
- Node.js 20+
- Docker (for PostgreSQL)
- Make

### 1. Setup

```bash
# Install backend and frontend dependencies
make install
```

This creates a Python virtual environment (`.venv`) if needed and installs all dependencies.

### 2. Configure environment

```bash
# Copy the example env file
cp backend/etc/.env.example backend/etc/.env

# Edit backend/etc/.env and set:
# - BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD
# - BOOTSTRAP_SUPER_ADMIN_EMAIL / BOOTSTRAP_SUPER_ADMIN_PASSWORD
# - API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY) as needed
```

All backend configuration lives in `backend/etc/.env`. This single file is used by both the backend application and Docker Compose.

### 3. Run

```bash
# Start PostgreSQL, backend, and frontend
make dev
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8001
- API Docs: http://localhost:8001/docs

## Make Targets

### Local Development

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies |
| `make dev` | Start DB + backend + frontend |
| `make backend` | Start DB + backend only |
| `make frontend` | Start frontend only |
| `make db` | Start PostgreSQL container (port 5455) |
| `make db-stop` | Stop PostgreSQL container |
| `make clean` | Clean build artifacts |

### Docker (Full Stack)

| Command | Description |
|---------|-------------|
| `make docker-up` | Start all Docker containers |
| `make docker-down` | Stop all containers |
| `make docker-logs` | View container logs |
| `make docker-ps` | Show running containers |
| `make docker-clean` | Remove containers and volumes |
| `make migrate-db` | Run database migrations |

## Linting & Formatting (uv + ruff + pre-commit)

All Python tooling lives in `backend/`. Configuration:

- `backend/pyproject.toml` — ruff lint/format rules, dev dep group
- `backend/uv.lock` — pinned dev tool versions
- `backend/.pre-commit-config.yaml` — hook definitions (ruff lint, ruff-format, basic hygiene)
- `backend/.venv/` — uv-managed virtual environment (auto-created, gitignored)

### How the virtualenv is created

`uv sync` reads `backend/pyproject.toml` + `backend/uv.lock`, creates `backend/.venv/` if missing, and installs the requested groups. No manual `python -m venv` step. The directory is reproducible — delete it any time and rerun `uv sync`.

> **Note:** This `backend/.venv/` is the uv-managed env for dev tooling (ruff, pre-commit, pyright). The legacy `make install` target still creates a separate `.venv` at repo root via `pip` — Makefile migration to uv is pending.

### One-time setup

```bash
cd backend
uv sync --group dev                    # creates .venv, installs dev tools
uv run pre-commit install -c .pre-commit-config.yaml   # registers git hook
```

The hook auto-runs ruff lint + format on staged Python files at every `git commit`.

### Daily commands (run from `backend/`)

| Command | Purpose |
|---------|---------|
| `uv sync --group dev` | Install/update dev tools |
| `uv run ruff check .` | Lint |
| `uv run ruff check . --fix` | Lint + autofix |
| `uv run ruff format .` | Format |
| `uv run pre-commit run --all-files` | Run all hooks manually |
| `uv run pre-commit autoupdate` | Bump hook versions |

### Scoped to one folder

```bash
uv run ruff check agent/ --fix
uv run ruff format agent/
```

### TODO

- Makefile targets for `lint`, `format`, `precommit-install`, and migrate `install-backend` to use `uv sync` instead of `pip install -r requirements.txt`.

## Project Structure

```
state-machine/
├── backend/
│   ├── agent/            # AI agent definitions and sessions
│   ├── auth/             # Authentication (local, Google, Microsoft SSO)
│   ├── bootstrap/        # Startup provisioning (schema, migrations, seed)
│   ├── common/           # Shared config, logging, utilities
│   ├── entities/         # Domain entities and state management
│   ├── organizations/    # Multi-tenant organization management
│   ├── workflow/         # State machine definitions and transitions
│   ├── alembic/          # Database migrations
│   ├── etc/              # Environment config (.env, config.ini)
│   ├── main.py           # Application entrypoint
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── pages/        # Page components
│   │   ├── layouts/      # Layout components
│   │   └── services/     # API client
│   └── package.json
├── docker-compose.local.yml    # Local development Docker Compose
├── docker-compose.prod.yml     # Deployment Docker Compose
├── Makefile
└── design_docs/          # Architecture and design documents
```

## Environment Configuration

All configuration lives in **`backend/etc/.env`** (template: `backend/etc/.env.example`).

Key variables:

### Core (required)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://statemachine:statemachine@localhost:5455/statemachine` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | — | JWT signing secret. **Required in production.** |
| `ENCRYPTION_KEY` | falls back to `JWT_SECRET_KEY` | Encryption key for sensitive credentials stored in the database. Set separately from `JWT_SECRET_KEY` if you want independent rotation. |
| `FRONTEND_URL` | `http://localhost:5173` | Public URL of the frontend. **Must be set to the production URL on the VM** — if missing, all email form links will point to localhost. |
| `PORT` | `8001` | Backend server port |
| `ENVIRONMENT` | `local` | Runtime environment label (`local`, `production`, etc.) |

### Bootstrap / Seed (required on first run)

| Variable | Default | Description |
|----------|---------|-------------|
| `BOOTSTRAP_ADMIN_EMAIL` | — | Initial admin user email |
| `BOOTSTRAP_ADMIN_PASSWORD` | — | Initial admin user password |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` | — | Super-admin email |
| `BOOTSTRAP_SUPER_ADMIN_PASSWORD` | — | Super-admin password |

### Database (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_APP_SCHEMA` | `public` | PostgreSQL schema that all application tables are created in. Alembic also stores `alembic_version` in this schema. Change to namespace multiple deployments in one database. |
| `ALEMBIC_CONFIG_PATH` | — | Path to `alembic.ini`. Defaults to the bundled config. Override when running migrations from outside the container. |
| `SQLALCHEMY_DATABASE_MIGRATION_URL` | falls back to `DATABASE_URL` | Separate DB URL used only for running Alembic migrations. Useful when the migration user needs different credentials or when the app DB hostname differs from the migration host (e.g. Docker vs localhost). |

### Email — SMTP (optional — required if email sending is used)

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | — | SMTP server port (usually 587 for TLS) |
| `SMTP_USERNAME` | — | SMTP authentication username |
| `SMTP_PASSWORD` | — | SMTP authentication password |
| `SMTP_FROM_EMAIL` | — | Sender email address |
| `SMTP_FROM_NAME` | — | Sender display name |
| `SMTP_USE_TLS` | — | Set to `true` to enable TLS |
| `SMTP_REPLY_TO_EMAIL` | — | Reply-to address for outbound emails |
| `INBOUND_EMAIL_DOMAIN` | - | Domain for inbound email routing |
| `INBOUND_EMAIL_WEBHOOK_SECRET` | — | Webhook secret for inbound email callbacks |
| `INBOUND_EMAIL_ALLOWED_BUCKET` | — | S3 bucket for inbound email storage |
| `INBOUND_EMAIL_S3_REGION` | — | AWS region for inbound email S3 bucket |

### Auth / SSO (optional — required if SSO is enabled)

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | — | Google OAuth redirect URI |
| `GOOGLE_ALLOWED_DOMAIN` | — | Restrict Google login to this domain (e.g. `newtuple.com`) |
| `MICROSOFT_OAUTH_CLIENT_ID` | — | Microsoft OAuth app client ID |
| `MICROSOFT_OAUTH_TENANT_ID` | — | Microsoft OAuth tenant ID |
| `MICROSOFT_OAUTH_CLIENT_SECRET` | — | Microsoft OAuth client secret |
| `MICROSOFT_OAUTH_REDIRECT_URI` | `http://localhost:5173/auth/microsoft/callback` | Microsoft OAuth redirect URI |
| `MICROSOFT_OAUTH_STATE_SECRET` | — | Secret used to sign Microsoft OAuth state token |
| `MICROSOFT_OAUTH_STATE_TTL_SECONDS` | `600` | TTL for Microsoft OAuth state token |
| `ALLOW_REGISTRATION` | — | Set to `true` to allow self-registration |
| `BYPASS_AUTH` | — | Set to `true` to disable auth checks (local dev only) |

### Redis (required if background jobs or caching is used)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | — | Redis server hostname |
| `REDIS_PORT` | — | Redis server port |
| `REDIS_PASSWORD` | — | Redis authentication password |
| `REDIS_DB` | — | Redis database index |
| `REDIS_QUEUE_NAME` | — | Queue name for background job processing |

### AWS / S3 (optional — required if file storage is used)

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | — | AWS secret key |
| `S3_BUCKET_NAME` | — | S3 bucket for file uploads |
| `S3_REGION` | — | AWS region for S3 bucket |
| `S3_ENABLED` | — | Set to `true` to enable S3 file storage |

### AI / LLM (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_MODEL_NAME` | — | OpenAI model to use |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `ANTHROPIC_MODEL_NAME` | — | Anthropic model to use |
| `LITELLM_MODEL` | — | LiteLLM model identifier |
| `LITELLM_API_BASE` | — | LiteLLM API base URL |

### Outbound HTTP / SSRF (optional)

Outbound calls to caller-supplied URLs (connector base URLs, remote file fetches) are filtered
against private, loopback and reserved address space, and pinned to the IP that was validated so
a second DNS lookup cannot swap in another address. Leave the variable below unset on SaaS and
multi-tenant deployments.

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTBOUND_HTTP_ALLOWED_INTERNAL_IPS` | — | Comma-separated IPs/CIDRs the guard may reach inside private space, e.g. `10.252.5.4/32,172.18.0.0/16`. For self-hosted deployments with a co-located service. Listed addresses are still resolved and still IP-pinned; every other internal address stays blocked. Link-local (the cloud metadata endpoint) is always refused. |

Prefer a CIDR over a bare IP for container networks — Docker reassigns service IPs when a
container is recreated, so `172.18.0.3` stops matching while `172.18.0.0/16` keeps working.

## Database

PostgreSQL runs via Docker on port **5455** (mapped from container port 5432).

```bash
# Start database
make db

# Stop database
make db-stop

# Connect to database
psql -h localhost -p 5455 -U statemachine -d statemachine
```

Migrations run automatically on backend startup via Alembic.

## Documentation

- [design_docs/](design_docs/) - Architecture and design documents
