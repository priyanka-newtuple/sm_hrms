# Backend Implementation Progress

**Last Updated:** 22 January 2026
**Status:** Core Platform + Playbook Runtime + Projections + Funnel Builder + Agent Executor + TOOL Executor + Resume Upload + Form Config + Multi-Tenancy + Entity Type Registry + Extraction Configs + View Definitions + Generic Document Upload (Phase 1-3) + Document Processing Pipeline + Document Agent with Configurable Tools + Unified Agent Architecture + Multi-Organization Membership + Self-Service Tenant Creation + Calendar Integration & Interview Scheduling (v0.13) + **Requisition Entity & Job Prioritization (v0.14)** Complete

---

## Overview
The backend implements the **Platform Core** layer of the state machine workflow runtime. It provides a versioned state machine engine, playbook execution runtime, and observability foundations. The implementation follows a clean architecture with FastAPI, SQLAlchemy, and a service-oriented design pattern.

---

## Technology stack
- **Framework:** FastAPI 0.95.0+
- **ORM:** SQLAlchemy 1.4.0+
- **Database:** PostgreSQL target (SQLite for local development)
- **Python:** 3.12
- **AI Integration:** Anthropic Claude API + MCP (Model Context Protocol)
- **Architecture:** Service layer pattern with dependency injection and immutable context objects.
- **Migrations:** Alembic for versioned schema management.

---

## Completed components

### 1. Platform Core (100% Complete)
- **Data Models**: Implementation of Entity, EntityRelation, EntityState, EntityEvent, StateMachine, StateTransition, Intervention, and Signal.
- **Transition Engine**: Atomic state updates with guard evaluation, side effects (signals), and optimistic locking.
- **Guard Engine**: Support for FIELD_PRESENT, RELATION_EXISTS, POLICY_CHECK, EXTERNAL_CHECK, and HITL_REQUIRED.
- **SLA Engine**: Automated calculation of deadlines based on state machine definitions.

### 2. Playbook Runtime (Phase 1 Complete)
- **Playbook Models**: Versioned definitions, runs, and individual step execution records.
- **Orchestration Service**: Lifecycle management (start, pause, resume, cancel) and automated step advancement.
- **Output Aggregation**: Merging individual step results into the main playbook run output.

### 3. Observability & Infrastructure
- **Structured Logging**: JSON-formatted logs with request-scoped correlation IDs.
- **Error Handling**: Standardized error response schema with unique error codes and tracing context.
- **Database Migrations**: Alembic setup with baseline and playbook schema versions.
- **Testing**: 267 tests including unit tests for all services and end-to-end API integration tests.

### 4. API Layer
- **REST Endpoints**: Complete CRUD and operational endpoints for all core resources.
- **Bulk Operations**: Dedicated endpoint for multi-entity state transitions.
- **Transition Visibility**: Dry-run guard evaluation and available transitions endpoint.

### 5. Projections Layer
- **Pipeline View**: Denormalized read model for Kanban board (single-query pipeline data).
- **SLA Heatmap**: Aggregated metrics by job/state for dashboards.
- **Sync Updates**: Automatic projection updates on entity creation, transitions, and relations.
- **SLA Risk Computation**: Automatic categorization (CRITICAL/WARNING/OK) based on deadline proximity.
- **Multi-Funnel Tracking**: Pipeline view includes `machine_name`/`machine_version` for funnel detection; `GET /projections/pipeline-funnels` endpoint for aggregated funnel info.

### 6. Funnel Builder Backend (FUNNEL-MULTI-001)
- **Domain Config API**: `/config/funnels` endpoints for ATS-specific funnel management.
- **Naming Enforcement**: Machine name pattern `ats_application_*` with validation.
- **Definition Validation**: Comprehensive validation with blocking errors and non-blocking warnings.
- **Version Management**: Draft/published semantics with automatic version increment.
- **State Graph Analysis**: Reachability, orphan detection, terminal state validation.

### 7. Agent Executor (AGENT_CALL)
- **MCP Server**: Model Context Protocol server exposing platform tools to AI agents:
    - Entity tools: `get_entity`, `update_entity`, `list_entities`, `get_entity_state`
    - Transition tools: `get_available_transitions`, `execute_transition`
    - Relation tools: `create_relation`, `list_relations`
    - Intervention tools: `create_intervention`, `list_interventions`
    - Signal tools: `create_signal`, `list_signals`
    - Event tools: `list_events`
- **LiteLLM Integration**: PlaybookAgentExecutor using LiteLLM for model-agnostic AI:
    - Supports Anthropic Claude, OpenAI GPT-4, Ollama local models, and more
    - OpenAI-compatible tool format for cross-provider compatibility
    - Agentic loop with configurable max iterations
    - Template variable substitution in prompts
    - Automatic tool call handling and result aggregation
- **Audit Logging**: AgentToolCall model for recording all tool invocations:
    - Tool name, arguments, results, success/failure, duration
    - Step and run correlation for traceability
- **Playbook Integration**: execute_step() now fully supports AGENT executor type:
    - Automatic step completion/failure based on agent result
    - Output aggregation into playbook run outputs
- **Configuration**: Environment variables for API key, model, and max iterations:
    - `LITELLM_MODEL`: Model to use (default: claude-sonnet-4-20250514)
    - `ANTHROPIC_API_KEY`: API key for Claude (read by LiteLLM)
    - `OPENAI_API_KEY`: API key for OpenAI (read by LiteLLM)
    - `LITELLM_API_BASE`: Optional custom API base URL
    - `AGENT_MAX_ITERATIONS`: Max agentic loop iterations (default: 10)

### 8. TOOL Executor (TOOL_CALL) ✅ COMPLETE
- **Extensible Framework**: Plugin-based tool executor for playbook TOOL steps:
    - `ToolHandler` protocol for implementing new tool handlers
    - `ToolRegistry` for handler registration and discovery
    - `@register_handler` decorator for auto-registration
    - `ToolExecutionResult` for standardized results
- **Variable Substitution**: Template variables in tool configs:
    - `{{entity_id}}`, `{{entity_type}}` - Entity context from playbook run
    - `{{playbook_name}}`, `{{run_id}}`, `{{step_name}}` - Run context
    - `{{input.field_name}}` - Access playbook run inputs
    - `{{output.field_name}}` - Access outputs from previous steps
    - Recursive substitution in nested dicts and lists
- **Built-in Tool Handlers**:
    - `send_email`: Integrates with EmailService (SMTP/SES)
        - Config: `to`, `subject`, `body_html`, `body_text`, `reply_to`
        - Uses organization's configured email provider
    - `http_request`: Generic HTTP/webhook calls via httpx
        - Config: `url`, `method`, `headers`, `json_body`, `query_params`, `timeout`, `expected_status`, `extract_fields`
        - Supports GET, POST, PUT, PATCH, DELETE
        - Configurable timeout (max 120s) and status code validation
    - `action`: Wraps existing ActionExecutor for internal actions
        - Config: `action_type` + action-specific fields
        - Supports: `create_entity`, `update_entity`, `find_or_create`, `link_entity`, `run_playbook`, `add_comment`
- **Audit Logging**: `ToolCallLog` model for tracking all tool invocations:
    - Tool name, resolved config, result, success/failure, duration
    - Step and run correlation for traceability
    - Organization scoping for multi-tenant support
- **Playbook Integration**: `execute_step()` now fully supports TOOL executor type:
    - Automatic step completion/failure based on tool result
    - Output stored in step_run.outputs for subsequent steps
- **Files Created**:
    - `app/tools/__init__.py` - Public API exports
    - `app/tools/result.py` - ToolExecutionResult dataclass
    - `app/tools/base.py` - ToolHandler protocol, ToolExecutionContext
    - `app/tools/registry.py` - ToolRegistry, @register_handler
    - `app/tools/executor.py` - PlaybookToolExecutor with variable substitution
    - `app/tools/handlers/email_handler.py` - send_email tool
    - `app/tools/handlers/http_handler.py` - http_request tool
    - `app/tools/handlers/action_handler.py` - action tool
    - `app/models/tool_call_log.py` - Audit log model
    - `alembic/versions/023_add_tool_call_logs.py` - Migration
    - `tests/test_tool_executor.py` - 25 tests

### 9. Calendar Integration (v0.13) ✅ COMPLETE
- **Google Calendar OAuth 2.0**: Full OAuth flow with popup-based authentication
    - `GET /integrations/google-calendar/auth-url` - Initiates OAuth popup flow
    - `GET /integrations/google-calendar/callback` - Handles code exchange
    - `DELETE /integrations/google-calendar/disconnect` - Revokes access
    - `GET /integrations/google-calendar/status` - Returns connection status
- **UserIntegration Model**: Per-user OAuth token storage with Fernet encryption
- **CalendarService**: Dual-provider abstraction with automatic fallback:
    - `GoogleCalendarProvider` - Uses Google Calendar API v3
    - `ICSEmailProvider` - RFC 5545 .ics files via SMTP
- **MCP Tool: `send_calendar_invite`**: Available to playbooks and document agents
    - Parameters: title, date, start_time, duration_minutes, attendees, description, location, timezone
    - Supports template variable substitution
- **Scheduling API** (ATS convenience endpoint):
    - `POST /scheduling/applications/{application_id}/interviews`
    - Auto-generates title from candidate/job data
    - Creates audit event in application timeline
- **Files Created**:
    - `app/models/user_integration.py` - OAuth token storage
    - `app/services/calendar/base.py` - CalendarEvent, CalendarResult
    - `app/services/calendar/service.py` - CalendarService orchestration
    - `app/services/calendar/google_calendar.py` - Google Calendar provider
    - `app/services/calendar/ics_email.py` - ICS email fallback
    - `app/services/calendar/tools.py` - MCP tool handler
    - `app/api/routes/integrations.py` - OAuth endpoints
    - `app/schemas/scheduling.py` - Scheduling request/response schemas
    - `app/api/routes/scheduling.py` - Interview scheduling endpoint
    - `alembic/versions/025_add_user_integrations.py` - Migration

---

## Future work

### Phase 2: Orchestration & Projections
- [x] **AGENT_CALL Executor**: LLM reasoning + tool access via MCP server + structured output.
- [x] **TOOL_CALL Executor**: Integration handlers for email, HTTP/webhooks, and internal actions.
- [ ] **Remaining Executors**:
    - `HITL_WAIT`: Logic to pause playbooks until a linked Intervention is resolved.
    - `TIMER_WAIT`: Time-based delays for follow-up automations.
- [x] **External Adapters**: Connectors for external services:
    - Calendar providers (Google Calendar) - see **Calendar Integration** section below ✅
    - Assessment platforms - can be added as new tool handlers.
- [x] **Projections Layer**: High-performance read models to avoid client-side joins:
    - `ats_pipeline_view`: Denormalized view with application_id, candidate_name, job_title, current_state, SLA risk.
    - `ats_sla_heatmap`: Aggregated counts of applications and SLA breaches per job/state.
    - Synchronous projection updates on entity creation, transitions, and relation changes.
    - API endpoints: `GET /projections/pipeline`, `GET /projections/heatmap`, `POST /projections/heatmap/refresh`.
- [ ] **Event Consumer**: Background worker (Celery/TaskIQ) to process the `entity_events` stream and update projection tables in near real-time.
- [ ] **Schema Validation**: Robust JSON Schema validation for state machine and playbook definitions to catch logic errors at design-time.
- [x] **Transition Visibility API Support**: Backend endpoints to support frontend transition visibility features:
    - **GET `/entities/{entity_id}/transitions/available`**: Return all available transitions from current state with:
        - Trigger name and human-readable label.
        - Target state.
        - Guard definitions and current pass/fail status.
        - Guard failure reasons (if any guards fail).
        - Guard descriptions for UI display.
    - **Guard Evaluation Service Enhancement**: Extend `guard_service.py` to support "dry-run" guard evaluation:
        - Evaluate guards without executing transition (for UI preview).
        - Return detailed guard reports with pass/fail status and failure messages.
        - Support entity context for accurate guard evaluation (entity data, relations, interventions).
    - **Transition Metadata**: Enhance transition response schema to include:
        - Guard requirements as structured data (not just pass/fail).
        - Human-readable guard descriptions.
        - Guard parameter values for display (e.g., "Score >= 80" instead of raw JSON).

- [x] **FUNNEL-MULTI-001 — Multi-funnel per Job (different machine names) + Funnel Builder backend support (domain-safe)**:
    - **Goal**: Support multiple funnel definitions (different `machine_name`s) and job-level assignment without compromising the generalized state machine engine.
    - **Design constraint**: Keep `/state-machines` as the generic API (no ATS-specific assumptions). Funnel Builder uses a dedicated "domain config" API that enforces naming and validation.
    - **Implementation**:
        - **Naming convention enforcement**: `machine_name` regex `^ats_application_[a-z0-9]+(?:_[a-z0-9]+)*$`, max 128 chars.
        - **API endpoints** (`/config/funnels`):
            - `POST /config/funnels` - Create new funnel
            - `PUT /config/funnels/{machine_name}` - Update (in-place for draft, new version for published)
            - `POST /config/funnels/validate` - Dry-run validation
            - `GET /config/funnels` - List funnels with version summaries
            - `GET /config/funnels/{machine_name}` - Get funnel (latest or specific version)
            - `GET /config/funnels/{machine_name}/versions` - List all versions
            - `POST /config/funnels/{machine_name}/{version}/publish` - Publish version
        - **Validation errors** (blocking): MISSING_INITIAL_STATE, MISSING_TRANSITIONS, UNKNOWN_STATE, INVALID_INITIAL_STATE, INVALID_GUARD_SCHEMA.
        - **Validation warnings** (non-blocking): UNREACHABLE_STATE, TERMINAL_WITH_OUTGOING, ORPHANED_STATE.
        - **Draft/Published semantics**: `is_active=False` = draft (mutable), `is_active=True` = published (immutable, edits create new version).
    - **Job-level funnel assignment (no schema changes)**:
        - Store funnel key in Job entity `data`: `pipeline_machine_name`, `pipeline_machine_version`.
        - Applications created for that job pass `machine_name/version` into entity creation (already supported).

### Authentication & Authorization (Complete)
- [x] **Dependencies**: Add `python-jose[cryptography]`, `bcrypt`, `python-multipart`, `authlib`, `httpx` to requirements.
- [x] **Configuration** (`app/core/config.py`):
    - JWT settings: `JWT_SECRET_KEY`, `JWT_ALGORITHM` (HS256), `ACCESS_TOKEN_EXPIRE_MINUTES` (30), `REFRESH_TOKEN_EXPIRE_DAYS` (7).
    - Google OAuth settings: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `GOOGLE_ALLOWED_DOMAIN` (optional domain restriction).
- [x] **User Model** (`app/models/user.py`):
    - `User` table: id, email (unique), hashed_password (nullable for Google users), full_name, avatar_url, role (enum: admin/recruiter/hiring_manager/viewer), auth_type (enum: local/google), google_id, is_active, last_login_at, created_at, updated_at.
    - `RefreshToken` table: id, user_id (FK), token_hash, expires_at, revoked, created_at.
    - Alembic migration for new tables.
- [x] **Auth Utilities** (`app/core/security.py`):
    - Password hashing with bcrypt directly (SHA256 pre-hash to handle any password length).
    - JWT creation (access token, refresh token).
    - JWT validation and decoding.
    - Refresh token generation and validation.
- [x] **Auth Routes** (`app/api/routes/auth.py`):
    - `POST /auth/login`: Local email/password login → returns access_token, refresh_token, user.
    - `POST /auth/register`: Create local user (configurable: open or admin-only).
    - `POST /auth/refresh`: Exchange refresh token for new access token.
    - `POST /auth/logout`: Revoke refresh token.
    - `GET /auth/me`: Get current user profile.
    - `GET /auth/google/url`: Generate Google OAuth authorization URL.
    - `POST /auth/google/callback`: Exchange Google auth code for tokens, create/update user.
- [x] **Google OAuth Integration**:
    - Use `authlib` for OAuth 2.0 / OIDC flow.
    - Validate Google ID token and extract user info (email, name, picture, sub).
    - Optional domain restriction via `GOOGLE_ALLOWED_DOMAIN`.
    - Create new user on first Google login or link to existing user by email.
- [x] **Auth Dependencies** (`app/api/deps.py`):
    - `get_current_user()`: Validate JWT from Authorization header, return User.
    - `get_current_active_user()`: Ensure user.is_active is True.
    - `require_roles(*roles)`: Dependency factory for role-based access control.
- [x] **Route Protection** (all API endpoints now require authentication):
    - All endpoints require `Depends(get_current_user)` for authentication.
    - Role-based access control applied per endpoint:
        - **Admin only**: State machine CRUD (`/state-machines`), funnel config (`/config/funnels`).
        - **Recruiter or Admin**: Entity CRUD, playbook management, signal/intervention creation, bulk transitions.
        - **Hiring Manager or above**: Execute transitions, decide interventions.
        - **Any authenticated user**: Read operations (list entities, view pipeline, list events).
- [x] **Auth Event Logging**: Record login attempts, token refresh, logout in entity_events for audit trail.
    - `AuthEventType` enum with event types: LOGIN_SUCCESS, LOGIN_FAILED, REGISTER, LOGOUT, TOKEN_REFRESH, TOKEN_REFRESH_FAILED, GOOGLE_LOGIN, GOOGLE_LOGIN_FAILED, etc.
    - `log_auth_event()` method in AuthService writes to entity_events table with entity_type="platform.user".
    - All auth routes log events with correlation_id for request tracing.
    - Failed attempts logged with reason for security monitoring.

### Multi-Organization Membership & Self-Service Tenant Creation ✅ COMPLETE (20 January 2026)
- [x] **UserOrganization Junction Table** (`models/user.py`):
    - `UserOrganization` model for many-to-many user-organization membership.
    - Each membership has its own `role` and `status` per organization.
    - Unique constraint on `(user_id, organization_id)` to prevent duplicates.
    - User's `organization_id` field indicates their current/active organization.
- [x] **Self-Service Tenant Creation** (`/auth/register-with-org`):
    - Users can register and create their own organization in one step.
    - New organizations start in `PENDING` status until super-admin approval.
    - User becomes admin of their pending organization.
    - Validation prevents users from creating multiple pending org requests.
- [x] **Super-Admin Organization Management** (`/organizations`):
    - Super-admins (Platform org admins) can view all organizations.
    - `GET /organizations/pending` - List organizations awaiting approval.
    - `POST /organizations/{id}/approve` - Approve pending organization.
    - `POST /organizations/{id}/reject` - Reject pending organization.
    - Email notifications sent to org requester on approval/rejection.
- [x] **Organization Switching** (`/users/me/organizations`):
    - `GET /users/me/organizations` - List all organizations user belongs to.
    - `POST /users/me/organizations/switch` - Switch active organization.
    - Switching updates user's `organization_id` and `role` to match membership.
- [x] **Super-Admin Config Override** (`get_org_id_admin` dependency):
    - Super-admins can view/manage config for any organization.
    - Optional `org_id` query parameter on config endpoints.
    - Non-super-admins can only access their own organization.
    - Applied to: LLM config, email config, form config, document config, general config.
- [x] **Notification Service Enhancements**:
    - `send_new_org_notification_to_superadmins()` - Notify super-admins of new org requests.
    - `send_org_approved_notification()` - Notify user when org approved.
    - `send_org_rejected_notification()` - Notify user when org rejected.

### Data Import & AI Extraction
- [x] **LiteLLM Integration**: Replace direct Anthropic Claude dependency with LiteLLM for model compatibility:
    - Configure LiteLLM as the model abstraction layer.
    - Support multiple LLM providers (OpenAI, Anthropic, local models) via unified API.
    - Update `PlaybookAgentExecutor` to use LiteLLM instead of direct Claude calls.
    - Environment variable `LITELLM_MODEL` to specify model (e.g., `claude-sonnet-4-20250514`, `gpt-4o`, etc.).
    - OpenAI-compatible tool format for cross-provider compatibility.
- [ ] **Bulk CSV/Spreadsheet Import** (`/import/csv`):
    - **Endpoint**: `POST /import/csv` - Upload CSV/Excel file for candidates or applications.
    - **LLM Column Mapping**: Use LLM to intelligently map arbitrary spreadsheet columns to entity fields:
        - Send column headers + sample rows to LLM.
        - LLM returns mapping: `{"Name": "candidate_name", "Email Address": "candidate_email", ...}`.
        - Support for unmapped columns → stored in `data` JSON field.
    - **Preview Response**: Return parsed rows with mapped fields for user confirmation.
    - **Batch Creation**: `POST /import/csv/confirm` - Create entities from confirmed mapping.
    - **Validation**: Email format, required fields, duplicate detection.
    - **Transaction Safety**: All-or-nothing batch creation with rollback on errors.
- [x] **Resume Extraction Service** (`/resumes`):
    - **Endpoint**: `POST /resumes/upload` - Upload up to 20 PDF resumes.
    - **LLM Extraction**: Use LiteLLM to extract:
        - Basic info: name, email, phone, location, LinkedIn URL.
        - Skills: free-form list of skills.
        - Experience: list of {company, title, start_date, end_date, description}.
        - Education: list of {institution, degree, field, graduation_year}.
        - Summary: brief professional summary.
    - **Structured Output**: Return JSON schema-validated extraction result.
    - **Confidence Scores**: Confidence indicator (0-1) for extracted data quality.
- [x] **Bulk PDF Upload** (`/resumes`):
    - **Endpoint**: `POST /resumes/upload` - Upload multiple PDF files (max 20).
    - **Async Processing**: Queue PDFs for extraction, return job ID.
    - **Status Endpoint**: `GET /resumes/jobs/{job_id}` - Check processing status.
    - **Results Endpoint**: `GET /resumes/jobs/{job_id}/results` - Get extracted candidates for preview.
    - **Preview Endpoint**: `GET /resumes/preview/{file_id}` - Stream PDF for inline preview.
    - **Confirm Endpoint**: `POST /resumes/confirm` - Create candidates from confirmed extractions.
    - **Delete Endpoint**: `DELETE /resumes/jobs/{job_id}` - Clean up job and files.
    - **Duplicate Detection**: Flag candidates with matching email addresses.
- [x] **File Storage Service**:
    - Abstract file storage interface (MinIO/local filesystem for dev, S3/GCS for production).
    - `FileStorageService` with upload, get, delete, and presigned URL methods.
    - Store uploaded resumes in configurable folder (default: `uploads/`).
- [ ] **Auto-Apply to Job** (Follow-up):
    - Optionally select a job during resume upload flow.
    - Automatically create Application entities linking new candidates to selected job.
    - Create entity relations (Candidate → Application, Job → Application).
    - Apply default funnel from job configuration.

### Generic Document Upload System (Phase 1 Complete)
- [x] **Document Type Configuration** (`/config/document-types`):
    - **Database Model**: `DocumentTypeConfig` table storing per-type settings:
        - `type_id`: Unique identifier (resume, email_thread, transcript, assignment, cover_letter, other)
        - `display_name`: Human-readable name
        - `folder`: Storage folder for files
        - `allowed_extensions`: Valid file types ([".pdf", ".txt"])
        - `max_size_mb`: Maximum file size
        - `extract_enabled`: Whether to run AI extraction
        - `system_prompt`: LLM system message for extraction
        - `extraction_prompt`: Custom LLM prompt template with {text} placeholder
        - `extraction_schema`: Expected JSON output structure
        - `is_system`: Boolean flag marking system document types that cannot be deleted (v0.14.0)
    - **Seed Defaults**: resume (with extraction, marked as system type), email_thread, transcript, assignment, cover_letter, other (storage only)
    - **API Endpoints**: GET/POST/PUT/DELETE for document type CRUD, POST /seed for seeding defaults
    - **System Type Protection**: Delete operation rejects attempts to delete system document types (v0.14.0)
- [x] **Generic Document Service** (`/documents`):
    - **Upload**: `POST /documents/upload?entity_id=X&document_type=Y` - Upload files to any entity
    - **Preview**: `GET /documents/{entity_id}/{document_id}` - Stream document for viewing
    - **Preview by Key**: `GET /documents/preview/{storage_key}` - Stream by storage key (backward compat)
    - **Delete**: `DELETE /documents/{entity_id}/{document_id}` - Remove document from entity and storage
    - **List**: `GET /documents/entity/{entity_id}` - List all documents for entity
    - **Metadata**: `GET /documents/metadata/{entity_id}/{document_id}` - Get document metadata only
    - **Storage**: Documents stored in `entity.data.documents[]` array with metadata
    - **AI Extraction**: Uses configurable system_prompt and extraction_prompt from DocumentTypeConfig
- [x] **Resume Upload Refactor** (Phase 2 Complete):
    - Resume upload `/confirm` endpoint now stores documents in `entity.data.documents[]` array
    - Candidate resume upload `/candidate/{id}/resume` also stores in `documents[]`
    - `update_candidate_from_resume` service updated to maintain `documents[]`
    - Full backward compatibility maintained: `resume_file_id` and `resume_storage_key` still work
    - Helper functions `_create_resume_document_metadata()` and `_add_document_to_entity()` added
- [ ] **Frontend UI** (Phase 3):
    - **DocumentTypesTab**: Settings tab for configuring document types
    - **CandidateDocuments**: Component showing all documents on a candidate
    - Upload dropdown to select document type before upload
    - Preview/download/delete actions on documents

### Form Configuration System (Complete)
- [x] **Form Schema Model** (`app/models/form_config.py`):
    - `FormSchema` table: id, entity_type (unique), schema (JSON), is_default, org_id, timestamps.
    - Stores field definitions with type, label, required, placeholder, validation rules.
    - Default schemas seeded for Candidate, Job, Application entity types.
- [x] **Picklist Model** (`app/models/form_config.py`):
    - `Picklist` table: id, name (unique), options (JSON array), org_id, timestamps.
    - Options: `[{value, label, active}]` for select/multi-select fields.
    - Default picklists seeded: department, location, source, employment_type.
- [x] **Form Config Service** (`app/services/form_config_service.py`):
    - CRUD operations for schemas and picklists.
    - `seed_defaults()`: Creates default schemas and picklists on startup.
    - Field type support: text, email, phone, url, number, date, textarea, select, multi_select, boolean.
- [x] **Form Config API** (`app/api/routes/form_config.py`):
    - `GET /form-config/schemas/{entity_type}`: Get form schema for entity type.
    - `PUT /form-config/schemas/{entity_type}`: Update form schema.
    - `GET /form-config/picklists`: List all picklists.
    - `GET /form-config/picklists/{id}`: Get picklist by ID.
    - `POST /form-config/picklists`: Create new picklist.
    - `PUT /form-config/picklists/{id}`: Update picklist.
    - `DELETE /form-config/picklists/{id}`: Delete picklist.

### Multi-Tenancy (Phase 1 Complete)
- [x] **Organization Model** (`app/models/organization.py`):
    - `Organization` table: id, name, slug (unique), domain (optional for SSO), settings (JSON), status, logo_url, timestamps.
    - `OrganizationStatus` enum: active, suspended, archived.
    - Domain-based automatic organization assignment for SSO users.
- [x] **Organization Scoping**:
    - Added `organization_id` foreign key to all 16 tenant-scoped tables:
        - Core: users, entities, entity_relations, entity_state, entity_events
        - State Machine: state_machines, state_transitions, interventions, signals
        - Playbooks: playbooks, playbook_runs, playbook_step_runs
        - Config: form_schemas, picklists
        - Audit: stage_comments, agent_tool_calls
    - Alembic migration (009) with automatic backfill to default organization.
- [x] **Organization Service** (`app/services/organization_service.py`):
    - CRUD operations: create, get, update, list organizations.
    - `ensure_default_organization()`: Creates default org on startup for single-tenant mode.
    - `get_organization_for_email()`: Domain-based org lookup for SSO.
    - `slugify()`: Auto-generate URL-safe slugs from org names.
- [x] **Organization API** (`app/api/routes/organizations.py`):
    - `GET /organizations/current`: Get current user's organization.
    - `GET /organizations`: List all organizations (admin only).
    - `POST /organizations`: Create new organization (admin only).
    - `GET /organizations/{id}`: Get organization by ID (admin only).
    - `PUT /organizations/{id}`: Update organization (admin only).
- [x] **Auth Dependencies** (`app/api/deps.py`):
    - `get_current_organization()`: Returns user's org, validates org is active.
    - `get_org_id()`: Convenience dependency for query filtering.
- [x] **Auth Service Updates**:
    - `create_local_user()` and `create_google_user()` now accept `organization_id`.
    - Auto-assigns users to org by email domain or default org.
- [x] **Startup Initialization**:
    - Default organization created automatically on app startup.
    - Existing data migrated to default organization.

### Phase 3: Enterprise & Scale
- [ ] **External ATS Sync**: Bi-directional synchronization with SoR (Greenhouse/Workday):
    - **Field-level ownership**: Define which system "owns" specific fields.
    - **Conflict resolution**: Logic for handling simultaneous updates in both systems.
    - **Idempotent writebacks**: Ensuring external updates don't trigger recursive transitions.
- [x] **Multi-tenant Isolation (Phase 1)**: Foundation for scaling to multiple customers:
    - Organization model with domain-based SSO support.
    - All tenant-scoped tables have `organization_id` column.
    - `get_current_organization` dependency for query filtering.
- [ ] **Multi-tenant Isolation (Phase 2)**: Resource-level permissions:
    - Job assignment table (user_id, job_id, role) for hiring manager scoping.
    - Query filtering to restrict hiring managers to assigned jobs only.
- [ ] **RBAC Implementation**: Fine-grained access control:
    - Permissions scoped to entity types (e.g., `Job.Read`, `Application.Transition`).
    - Role-based visibility for sensitive fields (PII).
- [ ] **Advanced Observability**: Enhanced tracing and monitoring:
    - **Distributed Tracing**: Tracking requests from Frontend → Backend → AI Agent → External Tool.
    - **Metrics**: Prometheus hooks for transition success rates, latency, and SLA breach counts.
- [ ] **PII Redaction**: Automatic masking of sensitive candidate data in logs and event payloads to ensure compliance (GDPR/SOC2).
- [ ] **Cost Tracking**: Real-time tracking of AI token usage and external API costs per agent/playbook run.

### Platform Refactoring: Configuration-Driven Architecture (Airtable Model)

The goal is to refactor from hardcoded ATS-specific logic to a fully **configuration-driven platform** where:
- Entity types are defined in database, not code
- Extraction configs (prompts, schemas) are stored in database
- Views/projections are configuration-driven
- "ATS" becomes a template that can be imported, not baked-in code

**Approach**: Incremental phases, no UI initially (API/seed-based configuration)

#### Current State Analysis

**Hardcoded ATS References (45+ files)**:
- `"ATS.Application"`, `"ATS.Candidate"`, `"ATS.Job"` throughout codebase
- `entity_service.py` (lines 30-34): `if entity_type == "ATS.Application"` triggers projection creation
- `transition_service.py` (line 325): ATS.Application check for projection update
- `projection_service.py`: Entire service hardcoded for ATS.Application
- `schemas/form_config.py` (lines 296-301): DEFAULT_SCHEMAS for 3 ATS types

**What's Already Generic**:
- `DocumentExtractionService` - accepts `ExtractionConfig` parameter ✓
- `BackgroundJobService` - domain-agnostic job queue ✓
- `Entity` model - flexible JSON `data` field ✓
- `StateMachine` - stored as JSON in database ✓
- `FormSchema`, `Picklist` - already configurable ✓
- `AIFeatureConfig` - model selection per feature ✓

---

#### Phase 1: Entity Type Registry ✅ COMPLETE

**Goal**: Remove hardcoded entity type strings, make types database-defined

**Status**: Complete (11 January 2026)
- Model: `models/entity_type.py` - EntityTypeDefinition with schema, relations, features ✅
- Schemas: `schemas/entity_type.py` - Full CRUD Pydantic schemas ✅
- Service: `services/entity_type_service.py` - CRUD + seeding + feature checks ✅
- Routes: `api/routes/entity_types.py` - Full REST API with admin protection ✅
- Migration: `015_add_entity_type_definitions.py` - Applied ✅
- Integration: `entity_service.py` and `transition_service.py` use `has_feature()` with backward-compatibility fallbacks ✅
- Tests: `tests/test_entity_type_service.py` - 25 tests (service + API) ✅
- Seeding: ATS entity types (Candidate, Job, Application) seeded on startup ✅
- Frontend: Types, API client, and `useEntityTypes` hook implemented ✅

**Phase 1 cleanup completed (11 January 2026)**:
- ✅ Removed backward-compatibility fallbacks in `entity_service.py` and `transition_service.py`
- ✅ Renamed `DEFAULT_SCHEMAS` to `ATS_DEFAULT_FORM_SCHEMAS` in `schemas/form_config.py` (clearly marked as ATS-specific, to be moved to templates in Phase 5)
- ✅ Updated `get_entity_type()` to handle namespaced lookups (e.g., "ATS.Application" → "Application")
- ✅ Updated `_build_entity()` to set `organization_id` from payload
- ✅ Updated projection tests to seed entity types before testing

**New Model: `EntityTypeDefinition`** (`models/entity_type.py`):
```python
class EntityTypeDefinition(Base):
    __tablename__ = "entity_type_definitions"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"))

    # Identity
    name = Column(String(64), nullable=False)           # "Candidate"
    display_name = Column(String(128))                  # "Job Candidate"
    description = Column(Text)

    # Schema
    schema = Column(JSON)                               # Field definitions
    # {"fields": [{"name": "first_name", "type": "string", "required": true}]}

    # Relations
    allowed_relations = Column(JSON)                    # Valid relation targets
    # [{"target_type": "Application", "relation_name": "applications", "cardinality": "one_to_many"}]

    # Workflow
    default_state_machine_id = Column(String(36), ForeignKey("state_machines.id"))

    # Features (which platform features this type uses)
    features = Column(JSON)
    # {"has_lifecycle": true, "has_projection": true, "has_form": true}

    # Display
    icon = Column(String(32))                           # Lucide icon name
    color = Column(String(7))                           # Hex color
```

**New Service: `EntityTypeService`** (`services/entity_type_service.py`):
- `get_entity_type(db, org_id, type_name) -> EntityTypeDefinition`
- `list_entity_types(db, org_id) -> List[EntityTypeDefinition]`
- `create_entity_type(db, org_id, definition) -> EntityTypeDefinition`
- `validate_entity_data(db, org_id, type_name, data) -> ValidationResult`
- `get_type_features(db, org_id, type_name) -> dict`

**API Routes** (`api/routes/entity_types.py`):
- `GET /entity-types` - List all entity types for org
- `GET /entity-types/{name}` - Get entity type definition
- `POST /entity-types` - Create entity type (admin)
- `PUT /entity-types/{name}` - Update entity type (admin)
- `DELETE /entity-types/{name}` - Delete entity type (admin)

**Refactor Entity Service** (remove hardcoded ATS checks):
```python
# BEFORE (lines 30-34):
if context.entity.entity_type == "ATS.Application":
    from app.services.projection_service import create_pipeline_view_for_application
    create_pipeline_view_for_application(db, context.entity, state)

# AFTER:
type_def = entity_type_service.get_entity_type(db, org_id, context.entity.entity_type)
if type_def and type_def.features.get("has_projection"):
    projection_service.create_projection_for_entity(db, context.entity, state, type_def)
```

**Seed Data: ATS Entity Types** (`seeds/ats_entity_types.py`):
- Candidate: `{features: {has_lifecycle: false, has_projection: false, has_form: true}}`
- Job: `{features: {has_lifecycle: true, has_projection: false, has_form: true}}`
- Application: `{features: {has_lifecycle: true, has_projection: true, has_form: true}}`

**Migration**: `015_add_entity_type_definitions.py`

**Files to Modify**:
| File | Change |
|------|--------|
| `models/entity_type.py` | NEW - EntityTypeDefinition model |
| `schemas/entity_type.py` | NEW - Pydantic schemas |
| `services/entity_type_service.py` | NEW - CRUD + validation |
| `api/routes/entity_types.py` | NEW - API endpoints |
| `services/entity_service.py` | Remove hardcoded ATS checks, use type features |
| `services/transition_service.py` | Remove hardcoded ATS checks |
| `schemas/form_config.py` | Remove DEFAULT_SCHEMAS, load from entity type |

---

#### Phase 2: Extraction Configs ✅ COMPLETE

**Goal**: Move extraction prompts/schemas from Python files to database

**Status**: Complete (11 January 2026)
- Implemented as `DocumentTypeConfig` (slightly different from original plan)
- Model: `models/document_config.py` - DocumentTypeConfig with `system_prompt` column ✅
- Schemas: `schemas/document.py` - Full CRUD schemas with `system_prompt` field ✅
- Service: `services/document_config_service.py` - CRUD + seeding ✅
- Routes: `api/routes/document_config.py` - `/config/document-types` endpoints ✅
- Migrations: `016_add_document_config.py`, `017_add_system_prompt_to_document_config.py` - Applied ✅
- Default document types seeded: resume, email_thread, transcript, assignment, cover_letter, other ✅
- `resume_upload_service.py` refactored to load extraction config from `DocumentTypeConfig` ✅
  - `_get_extraction_config()` method loads config from database
  - Falls back to hardcoded defaults if not in database
  - Extraction prompts now editable via API

**Future enhancements (not blocking)**:
- Add `post_actions` support (depends on Phase 4: Action Library)

**Original Plan - New Model: `ExtractionConfigModel`** (`models/extraction_config.py`):
```python
class ExtractionConfigModel(Base):
    __tablename__ = "extraction_configs"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"))

    # Identity
    name = Column(String(64), nullable=False)           # "resume_extractor"
    display_name = Column(String(128))                  # "Resume Parser"

    # File handling
    file_types = Column(JSON)                           # [".pdf", ".docx"]
    max_file_size_mb = Column(Integer, default=10)

    # Extraction
    system_prompt = Column(Text)                        # LLM system message
    extraction_prompt_template = Column(Text)           # User prompt with {text} placeholder
    json_schema = Column(JSON)                          # Expected output structure

    # Fallbacks
    fallback_patterns = Column(JSON)                    # Regex patterns
    # {"email": "[a-zA-Z0-9._%+-]+@...", "phone": "..."}

    # LLM params
    temperature = Column(Float, default=0.1)
    max_tokens = Column(Integer, default=2000)

    # Target entity
    target_entity_type = Column(String(64))             # "Candidate"
    field_mapping = Column(JSON)                        # Map extraction output → entity fields

    # Post-processing
    post_actions = Column(JSON)                         # Action chain after extraction
    # [{"action": "find_or_create", "entity_type": "Candidate", "match_on": ["email"]}]

    is_active = Column(Boolean, default=True)
```

**Refactor DocumentExtractionService**:
```python
def get_extraction_config(db, org_id, config_name) -> ExtractionConfig:
    """Load extraction config from database or return default."""
    db_config = db.query(ExtractionConfigModel).filter(...).first()
    if db_config:
        return ExtractionConfig(
            system_prompt=db_config.system_prompt,
            extraction_prompt_template=db_config.extraction_prompt_template,
            ...
        )
    return get_default_config(config_name)  # Fallback to hardcoded defaults
```

**Seed Data: Resume Extractor** (`seeds/ats_extraction_configs.py`):
```python
RESUME_EXTRACTOR = {
    "name": "resume_extractor",
    "display_name": "Resume Parser",
    "file_types": [".pdf"],
    "system_prompt": "You are a precise resume parser...",
    "extraction_prompt_template": "Extract candidate information...\n\n{text}",
    "json_schema": {...},
    "fallback_patterns": {"email": "...", "phone": "..."},
    "target_entity_type": "Candidate",
    "field_mapping": {"name": "first_name", "email": "email"},
    "post_actions": [{"action": "find_or_create", "entity_type": "Candidate", "match_on": ["email"]}]
}
```

**Migration**: `016_add_extraction_configs.py`

**Files to Modify**:
| File | Change |
|------|--------|
| `models/extraction_config.py` | NEW - ExtractionConfigModel |
| `services/extraction_config_service.py` | NEW - Load/save configs |
| `api/routes/extraction_configs.py` | NEW - API endpoints |
| `services/resume_upload_service.py` | Load config from DB instead of hardcoded |
| `services/resume_parser_service.py` | DEPRECATE - merge into generic flow |

---

#### Phase 3: View Definitions ✅ COMPLETE

**Goal**: Make projections/views configuration-driven, not hardcoded for ATS.Application

**Status**: Complete (11 January 2026)
- Model: `models/view_definition.py` - ViewDefinition + ProjectionRow models ✅
- Service: `services/view_definition_service.py` - CRUD + seeding with ATS defaults ✅
- Projection Service: `services/projection_service.py` - Fully rewritten to be config-driven ✅
- Migration: `018_add_view_definitions.py` - Creates `view_definitions` and `projection_rows` tables ✅
- Seeding: ATS view definitions (`application_pipeline`, `sla_heatmap`) seeded on startup ✅
- Backward compatibility: Wrapper functions maintain existing API signatures ✅
- Tests: All 242 tests passing ✅

**Key Changes**:

**New Model: `ViewDefinition`** (`models/view_definition.py`):
- Stores view configuration including source entity type, denormalized fields, SLA config, grouping, filters, and aggregations
- Per-organization scoping with unique constraint on (organization_id, name)

**New Model: `ProjectionRow`** (`models/view_definition.py`):
- Generic projection table replacing ATS-specific `AtsPipelineView`
- Composite primary key: (view_name, entity_id)
- Indexed columns: current_state, sla_due_at, sla_risk, machine_name
- Flexible `data` JSON column for denormalized fields from ViewDefinition config

**Refactored: `projection_service.py`**:
- `create_projection_for_entity(db, org_id, entity, state)` - Creates projection based on ViewDefinition
- `update_projection_on_transition(db, org_id, entity_id, ...)` - Updates projection on state change
- `sync_denormalized_fields_on_relation(db, org_id, entity_id, ...)` - Syncs related entity data
- `list_projections(db, org_id, view_name, ...)` - Lists projections with filters
- `aggregate_by_group(db, org_id, view_name, ...)` - Aggregates for heatmap views
- Field resolution: Handles `data.field` paths with fallbacks, datetime→ISO conversion
- Relation resolution: Finds related entities via EntityRelation, supports namespaced types

**Backward Compatibility Layer**:
- `create_pipeline_view_for_application()` - Wraps `create_projection_for_entity()`
- `update_pipeline_view_on_transition()` - Wraps `update_projection_on_transition()`
- `list_pipeline_view()` - Wraps `list_projections()` with org-agnostic query
- `aggregate_heatmap()` - Returns dict-based heatmap data

**ATS Default View Definitions** (seeded on startup):
```python
ATS_PIPELINE_VIEW = {
    "name": "application_pipeline",
    "display_name": "Hiring Pipeline",
    "source_entity_type": "Application",
    "denormalized_fields": [
        {"name": "candidate_id", "relation_type": "Candidate", "source_field": "entity_id"},
        {"name": "candidate_name", "relation_type": "Candidate", "source_field": "data.full_name", "fallback_field": "data.name"},
        {"name": "candidate_email", "relation_type": "Candidate", "source_field": "data.email"},
        {"name": "job_id", "relation_type": "Job", "source_field": "entity_id"},
        {"name": "job_title", "relation_type": "Job", "source_field": "data.title"},
        {"name": "job_department", "relation_type": "Job", "source_field": "data.department"},
    ],
    "sla_config": {"enabled": True, "warning_hours": 8, "critical_hours": 2},
    "group_by_field": "current_state",
}
```

**Files Modified/Created**:
| File | Change |
|------|--------|
| `models/view_definition.py` | NEW - ViewDefinition + ProjectionRow models |
| `services/view_definition_service.py` | NEW - CRUD + seeding |
| `services/projection_service.py` | REWRITTEN - Config-driven projections |
| `alembic/versions/018_add_view_definitions.py` | NEW - Migration |
| `app/main.py` | Added view definition seeding on startup |
| `app/models/__init__.py` | Export new models |
| `tests/test_projection_service.py` | Updated for new models |

---

### Generic Document Upload Feature ✅ COMPLETE (Phases 1-3)

**Goal**: Build a generic document upload system that supports multiple document types, optional AI extraction, and works with any entity type.

**Status**: Complete (11 January 2026)

#### Phase 1: Backend Infrastructure ✅
- **DocumentTypeConfig Model**: Database-driven configuration for document types
  - File: `models/document_config.py`
  - Stores type_id, display_name, folder, allowed_extensions, max_size_mb
  - AI extraction settings: extract_enabled, system_prompt, extraction_prompt, extraction_schema
  - Per-organization scoping
- **Document Config Service**: CRUD + seeding with defaults
  - File: `services/document_config_service.py`
  - Default types: resume, email_thread, transcript, assignment, cover_letter, other
- **Document Service**: Upload, list, preview, delete operations
  - File: `services/document_service.py`
  - Validates against DocumentTypeConfig
  - Stores documents in entity.data.documents[] array
  - Optional AI extraction via DocumentExtractionService
- **API Routes**:
  - `/config/document-types` - CRUD for document type configurations
  - `/documents/upload` - Upload document to entity
  - `/documents/entity/{id}` - List documents for entity
  - `/documents/{entity_id}/{document_id}` - Preview/download document
  - `/documents/metadata/{entity_id}/{document_id}` - Get document metadata
  - DELETE `/documents/{entity_id}/{document_id}` - Delete document
- **Migrations**: `016_add_document_config.py`, `017_add_system_prompt_to_document_config.py`

#### Phase 2: Resume Upload Refactoring ✅
- **Resume Upload Routes**: Updated to use document_service for storage
  - File: `api/routes/resume_upload.py`
  - New helper functions: `_create_resume_document_metadata()`, `_add_document_to_entity()`
  - `/confirm` endpoint stores resumes in documents[] array
  - `/candidate/{id}/resume` endpoint also uses documents[] array
- **Candidate Service**: Updated to maintain documents[] array
  - File: `services/candidate_service.py`
  - `update_candidate_from_resume()` now accepts user_id, filename parameters
  - Maintains both legacy fields (resume_file_id, resume_storage_key) and new documents[] array
- **Backward Compatibility**: Existing resume_file_id/resume_storage_key still work

#### Phase 3: Frontend UI ✅
- **API Integration**: Added document API methods
  - File: `frontend/src/core/services/api.ts`
  - `documents.upload()` - Upload document to entity
  - `documents.list()` - List documents for entity
  - `documents.getPreviewUrl()` - Get preview URL for iframe
  - `documents.getPreviewUrlByKey()` - Preview by storage key (backward compat)
  - `documents.delete()` - Delete document
- **Type Definitions**: Added DocumentMetadata types
  - File: `frontend/src/core/types/index.ts`
  - DocumentMetadata, DocumentUploadResponse, DocumentListResponse, DocumentDeleteResponse
- **Settings Tab**: DocumentTypesTab for managing document type configurations
  - File: `frontend/src/domains/ats/components/settings/DocumentTypesTab.tsx`
  - List/create/edit/delete document types
  - Configure allowed extensions, max size, AI extraction settings
  - Toggle active/inactive status
- **CandidateDocuments Component**: Documents list with upload/preview/delete
  - File: `frontend/src/domains/ats/components/CandidateDocuments.tsx`
  - Lists all documents attached to candidate
  - Upload dropdown with document type selection
  - Preview modal for PDFs
  - Delete confirmation
- **CandidatePreview Integration**: Documents section added to candidate preview
  - File: `frontend/src/domains/ats/components/CandidatePreview.tsx`
  - Shows all documents below candidate form
  - Compact mode for sidebar display

**Files Created**:
| File | Purpose |
|------|---------|
| `backend/app/models/document_config.py` | DocumentTypeConfig model |
| `backend/app/services/document_config_service.py` | Config CRUD + seeding |
| `backend/app/services/document_service.py` | Document operations |
| `backend/app/api/routes/document_config.py` | Config API endpoints |
| `backend/app/api/routes/documents.py` | Document API endpoints |
| `frontend/src/domains/ats/components/settings/DocumentTypesTab.tsx` | Settings UI |
| `frontend/src/domains/ats/components/CandidateDocuments.tsx` | Documents component |

**Files Modified**:
| File | Change |
|------|--------|
| `backend/app/api/routes/resume_upload.py` | Added document storage to confirm/upload |
| `backend/app/services/candidate_service.py` | Added documents[] array support |
| `frontend/src/core/services/api.ts` | Added documents API |
| `frontend/src/core/types/index.ts` | Added document types |
| `frontend/src/domains/ats/pages/SettingsPage.tsx` | Added Documents tab |
| `frontend/src/domains/ats/components/CandidatePreview.tsx` | Integrated documents |

---

### Document Processing Pipeline ✅ COMPLETE (Phase 1)

**Goal**: Build a unified document processing pipeline that supports:
- Multi-stage processing (EXTRACT → VALIDATE → ACTION)
- Declarative post-actions (create entity, run playbook, link entities)
- Job tracking for async processing
- Cross-skin support (ATS, CRM, Contract Management, Resource Management)

**Status**: Phase 1 Backend Complete (11 January 2026)

#### Phase 1: Backend Foundation ✅

**Enhanced DocumentTypeConfig Model**:
- New fields added to `models/document_config.py`:
  - `is_entity`: Whether documents of this type become first-class entities
  - `entity_type_name`: Entity type name if is_entity=True (e.g., "ATS.Resume")
  - `state_machine_name`: Optional state machine for document entities
  - `upload_contexts`: JSON array of upload context configurations
  - `agent_config`: JSON object with pipeline stages, validation rules, post-actions

**New DocumentProcessingJob Model** (`models/document_processing_job.py`):
- Tracks documents through processing pipeline
- Status: PENDING → EXTRACTING → VALIDATING → ACTIONING → COMPLETED / FAILED
- Stores results from each stage (extraction_result, validation_result, action_results)
- Tracks created entities and triggered playbooks
- Error tracking with retry support

**ActionExecutor Service** (`services/action_executor.py`):
- Declarative action execution engine
- Supported actions:
  - `create_entity`: Create new entity from extracted data
  - `update_entity`: Update existing entity with extracted data
  - `find_or_create`: Find by key fields or create new
  - `link_entity`: Create EntityRelation between entities
  - `run_playbook`: Trigger playbook with extracted data
- Field mapping support for transforming extracted data
- Condition evaluation for conditional action execution
- Context sharing between actions in chain

**DocumentPipelineService** (`services/document_pipeline_service.py`):
- Orchestrates full document processing pipeline
- Stages:
  1. EXTRACT: AI extraction using DocumentExtractionService
  2. VALIDATE: Validate against rules (required, email, phone, regex, etc.)
  3. ACTION: Execute post-actions from agent_config
- Job creation and tracking
- Progress reporting (0-100%)
- Error handling with stage identification
- Retry support for failed jobs

**API Endpoints** (`api/routes/documents.py`):
- `POST /documents/process`: Trigger document processing pipeline
- `GET /documents/jobs`: List processing jobs with filters
- `GET /documents/jobs/{job_id}`: Get specific processing job
- `POST /documents/jobs/{job_id}/retry`: Retry failed job

**Database Migration** (`alembic/versions/019_add_document_pipeline.py`):
- Adds new columns to document_type_configs table
- Creates document_processing_jobs table with indexes

**Updated Seed Data**:
- Default document types now include upload_contexts and agent_config
- Resume type configured with validation rules for name and email

**Files Created**:
| File | Purpose |
|------|---------|
| `backend/app/models/document_processing_job.py` | Processing job model |
| `backend/app/services/action_executor.py` | Declarative action executor |
| `backend/app/services/document_pipeline_service.py` | Pipeline orchestration |
| `backend/alembic/versions/019_add_document_pipeline.py` | Database migration |

**Files Modified**:
| File | Change |
|------|--------|
| `backend/app/models/document_config.py` | Added is_entity, upload_contexts, agent_config fields |
| `backend/app/models/__init__.py` | Export DocumentProcessingJob |
| `backend/app/schemas/document.py` | Added AgentConfig, PostAction, ValidationRule, processing job schemas |
| `backend/app/api/routes/documents.py` | Added processing job endpoints |
| `backend/app/services/document_config_service.py` | Updated seeds with new fields |

---

### Document Agent with Configurable Tools (13 January 2026) ✅ COMPLETE

**Overview**: Extends document processing with AI agent capabilities using MCP tools. Each document type can enable agent processing and configure which tools the agent can use.

**Tool Manifest System** (`services/tool_manifest.py`):
- Centralized tool definitions with metadata:
  - `name`: Tool identifier (e.g., "get_entity", "execute_transition")
  - `category`: Grouping (document, entity, workflow, communication, integration)
  - `description`: Human-readable description
  - `risk_level`: Safety classification (safe, moderate, caution)
  - `requires_confirmation`: Whether tool needs user confirmation
- Tool presets for quick configuration:
  - `minimal`: Read-only tools (get_entity, list_entities, get_entity_state)
  - `standard`: Minimal + entity updates (update_entity, create_relation)
  - `full`: All available tools including transitions and interventions
- API endpoint: `GET /api/document-types/tools` returns manifest with tools and presets

**Database Schema** (migrations 020, 021):
- `agent_enabled`: Boolean flag to enable agent processing
- `agent_prompt`: Custom instructions for the agent
- `agent_tools`: JSON array of enabled tool names

**DocumentAgentExecutor** (`services/document_agent_executor.py`):
- Filters available MCP tools based on document type configuration
- Uses `agent_tools` array to limit which tools agent can call
- Falls back to all tools if `agent_tools` is null/empty
- Executes agent with filtered tool set for document processing

**API Endpoints**:
- `GET /api/document-types/tools`: Returns tool manifest with categories and presets

**Files Created**:
| File | Purpose |
|------|---------|
| `backend/app/services/tool_manifest.py` | Tool definitions, categories, presets |
| `backend/alembic/versions/020_add_document_agent_fields.py` | agent_enabled, agent_prompt columns |
| `backend/alembic/versions/021_add_agent_tools_column.py` | agent_tools JSON column |

**Files Modified**:
| File | Change |
|------|--------|
| `backend/app/models/document_config.py` | Added agent_enabled, agent_prompt, agent_tools fields |
| `backend/app/schemas/document.py` | Added ToolDefinition, ToolPreset schemas |
| `backend/app/api/routes/document_config.py` | Added /tools endpoint |
| `backend/app/services/document_agent_executor.py` | Tool filtering based on config |

---

### Alembic Migration Fix (13 January 2026) ✅ COMPLETE

**Issue**: Production deployment failed with `value too long for type character varying(32)` error.

**Root Cause**: Alembic's `alembic_version` table uses VARCHAR(32) by default. Long revision IDs like `"017_add_system_prompt_to_document_config"` exceed this limit and get truncated, causing migration chain breaks.

**Fix Applied**:
1. **Production Database**: `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)`
2. **Codebase**: Shortened all revision IDs to numeric format (e.g., `"017"` instead of `"017_add_system_prompt_to_document_config"`)
3. **Documentation**: Added warning comment in `backend/alembic/env.py` about the VARCHAR(32) limitation

**Migrations Updated** (revision ID shortened):
- 013_add_ai_feature_config.py → revision "013"
- 014_add_background_jobs.py → revision "014"
- 015_add_entity_type_definitions.py → revision "015"
- 016_add_document_config.py → revision "016"
- 017_add_system_prompt_to_document_config.py → revision "017"
- 018_add_view_definitions.py → revision "018"
- 019_add_document_pipeline.py → revision "019"
- 020_add_document_agent_fields.py → revision "020"

---

#### Phase 2: Frontend & Multi-Skin ✅ PARTIALLY COMPLETE

**Completed** (13 January 2026):
- ✅ Enhanced DocumentTypesTab with agent configuration UI:
  - Agent processing toggle
  - Agent instructions textarea
  - Tool preset buttons (Minimal, Standard, Full)
  - Tool selection checkboxes grouped by category
  - Risk level badges (safe/moderate/caution)
  - Agent badge on document type cards

**Remaining**:
- Document upload across all entity types
- Upload context configuration in Settings
- Multi-skin support (CRM, Contract Management, Resource Management)
- Playbook integration for DOCUMENT_UPLOAD triggers

---

#### Phase 4: Action Library ~~❌ NOT STARTED~~ → SUPERSEDED

**Status**: Superseded by Unified Agent Architecture (14 January 2026)

The original Action Library proposal was to build a declarative post-processing system with a chain of actions (duplicate_check, find_or_create, create_entity, etc.). However, this duplicates functionality that already exists in the agent infrastructure.

**Why Superseded**:
- MCP tools already provide: `list_entities`, `create_entity`, `update_entity`, `create_relation`
- Document agents can already execute these tools based on instructions
- Building a separate declarative action system would duplicate the agent's capabilities
- Agent approach is more flexible (handles edge cases, can reason about decisions)

**Migration Path**: Configure document agents with appropriate instructions and tools instead of building a separate action chain system. The existing `DocumentTypeConfig.agent_prompt` and `agent_tools` fields provide this capability.

---

### Unified Agent Architecture ✅ COMPLETE (14 January 2026)

**Goal**: Consolidate three separate agent executors into a single unified infrastructure.

**Problem**: The codebase had three separate agent executors with significant code duplication:

| Executor | Purpose | Duplication |
|----------|---------|-------------|
| `PlaybookAgentExecutor` | Run AGENT playbook steps | ~250 lines |
| `DocumentAgentExecutor` | Process uploaded documents | ~250 lines |
| `UnifiedAgentExecutor` | Chat-style agent interactions | ~350 lines (most complete) |

All three had nearly identical:
- `_run_agent_loop()` methods
- `_get_openai_tools()` methods
- LiteLLM configuration
- API key resolution

**Solution**: Refactor `PlaybookAgentExecutor` and `DocumentAgentExecutor` to use `UnifiedAgentExecutor` internally.

**Implementation**:

1. **Added `session_mode` parameter to UnifiedAgentExecutor**:
   - `persistent` (default): Full session persistence with AgentSession/AgentMessage
   - `ephemeral`: No session persistence, single-shot execution for playbooks/documents

2. **Refactored PlaybookAgentExecutor**:
   - Now creates a temporary AgentDefinition from playbook step config
   - Uses UnifiedAgentExecutor with `session_mode="ephemeral"`
   - Maps result back to `AgentExecutionResult` for backward compatibility

3. **Refactored DocumentAgentExecutor**:
   - Creates temporary AgentDefinition from DocumentTypeConfig
   - Uses UnifiedAgentExecutor with `session_mode="ephemeral"`
   - Maps result back to `DocumentAgentResult` for backward compatibility

**Benefits**:
- Single codebase to maintain
- All features (approval workflow, tool filtering) available to all agent types
- Playbook agents can now use `require_approval` for dangerous tools
- Document agents can optionally persist session history
- Bug fixes benefit all use cases

**Files Modified**:
| File | Change |
|------|--------|
| `app/agent/unified_executor.py` | Added `session_mode` parameter |
| `app/agent/executor.py` | Refactored to use UnifiedAgentExecutor |
| `app/agent/document_agent.py` | Refactored to use UnifiedAgentExecutor |

---

### Calendar Integration ✅ COMPLETE (21 January 2026) - v0.13

**Goal**: Enable sending calendar invites directly from the application with optional Google Calendar OAuth for direct calendar integration.

**Architecture Decision**: **Platform Primitive** (not ATS-specific)
- Calendar invites are useful across multiple domains (ATS interviews, PMO meetings, CRM sales calls)
- Follows the same pattern as EmailService - abstraction with provider implementations
- Users without OAuth fall back to ICS-over-email

---

#### Phase 1: Foundation ✅ COMPLETE

**Model: `UserIntegration`** (`models/user_integration.py`):
- OAuth token storage per user/provider combination
- Encrypted access/refresh tokens
- Provider email and status tracking
- Migration: `025_add_user_integrations.py`

**Tasks Completed**:
- [x] UserIntegration model and migration
- [x] IntegrationService for CRUD (using Fernet encryption from existing crypto module)
- [x] Google OAuth flow endpoints:
    - `GET /integrations/google-calendar/auth-url` - Initiates OAuth popup flow
    - `GET /integrations/google-calendar/callback` - Handles OAuth code exchange
    - `DELETE /integrations/google-calendar/disconnect` - Revokes access and removes credentials
    - `GET /integrations/google-calendar/status` - Returns connection status for current user
- [x] Token refresh on API call failure (automatic retry with refreshed token)

---

#### Phase 2: Calendar Service ✅ COMPLETE

**CalendarService** (`services/calendar/service.py`):
- `CalendarEvent` dataclass for event data
- `CalendarResult` dataclass for responses (includes method used)
- `create_event()` - Tries Google Calendar first, falls back to ICS email

**Providers**:
- [x] `GoogleCalendarProvider` (`services/calendar/google_calendar.py`)
    - Uses Google Calendar API v3
    - Creates events with attendees, location, description
    - Sends invite emails via Google Calendar
    - Returns HTML link to view event
- [x] `ICSEmailProvider` (`services/calendar/ics_email.py`)
    - Generates RFC 5545 compliant .ics files
    - Sends via existing EmailService as MIME attachment
    - Sets proper Content-Type for calendar apps to recognize

**Provider Selection**:
- Automatically tries Google Calendar if user has valid integration
- Falls back to ICS email if Google not connected or API fails
- Response indicates which method was used

---

#### Phase 3: Tool Handler ✅ COMPLETE

**Tool: `send_calendar_invite`** (`services/calendar/tools.py`):
- Registered in document agent tool manifest
- Can be used by playbooks and agents for scheduling
- Parameters: title, date, start_time, duration_minutes, attendees, description, location, timezone
- Supports template variable substitution

**Configuration Example**:
```json
{
    "tool": "send_calendar_invite",
    "config": {
        "attendees": ["{{candidate_email}}", "{{interviewer_email}}"],
        "title": "Interview: {{candidate_name}} for {{job_title}}",
        "date": "2026-01-25",
        "start_time": "10:00",
        "duration_minutes": 60,
        "location": "{{meeting_link}}"
    }
}
```

---

#### Phase 4: Frontend ✅ COMPLETE

**Settings → Integrations Tab**:
- [x] `GoogleCalendarConnectButton` component showing connection status
- [x] OAuth popup flow with message passing for success callback
- [x] Connected state shows provider email
- [x] Disconnect button with confirmation

**Schedule Interview UI** (ATS-specific convenience):
- [x] `ScheduleInterviewModal` - Full form with date/time/duration/timezone/attendees
- [x] "Schedule" button on ApplicationDetail (prominent, cobalt blue)
- [x] Success state with Google Calendar link (when applicable)
- [x] Scheduling endpoint: `POST /scheduling/applications/{application_id}/interviews`
- [x] Audit event created in application timeline

---

#### Future Enhancement: Availability Checking

Once calendar is connected, enable availability checking for interview scheduling:
- Query free/busy for interviewers
- Show available slots in scheduling UI
- Prevent double-booking

---

#### Files Created

| File | Purpose |
|------|---------|
| `models/user_integration.py` | OAuth token storage |
| `services/calendar/base.py` | CalendarEvent and CalendarResult dataclasses |
| `services/calendar/service.py` | CalendarService with provider selection |
| `services/calendar/google_calendar.py` | Google Calendar API provider |
| `services/calendar/ics_email.py` | ICS email fallback provider |
| `services/calendar/tools.py` | `send_calendar_invite` MCP tool |
| `api/routes/integrations.py` | OAuth endpoints for Google Calendar |
| `schemas/scheduling.py` | Pydantic models for scheduling API |
| `api/routes/scheduling.py` | Interview scheduling endpoint |
| `alembic/versions/025_add_user_integrations.py` | Migration |
| `frontend/.../GoogleCalendarConnectButton.tsx` | OAuth connect UI |
| `frontend/.../ScheduleInterviewModal.tsx` | Scheduling form modal |

---

### Requisition Entity & Job Prioritization (v0.14) ✅ COMPLETE

**Goal**: Add a Requisition entity type to represent formal hiring requests, with priority-based ranking that cascades to linked Jobs. Enable drag-and-drop reordering in the UI.

**Architecture Decision**: **New Entity Type** (not primitive)
- Requisition is a domain entity (like Job, Candidate, Application)
- Uses existing `EntityTypeDefinition` system - no new tables needed
- Relations via `EntityRelation` to link Requisitions → Jobs
- Priority stored in `data.priority_score` field, cascaded to linked Jobs on update

**Key Design Choices**:
1. **No lifecycle/state machine** - Simple status field (OPEN/FILLED/CANCELLED), not a full workflow
2. **Priority on Requisition** - Jobs inherit priority from parent Requisition
3. **Drag-drop reordering** - Updates `priority_score` (0-100 numeric) for sort order
4. **One-to-many relation** - One Requisition can spawn multiple Jobs

---

#### Phase 1: Backend - Entity Type Definition ✅ COMPLETE

**Add Requisition to ATS_ENTITY_TYPES** (`services/entity_type_service.py`):

```python
{
    "name": "Requisition",
    "display_name": "Job Requisition",
    "description": "A formal request for hiring personnel for a specific position",
    "schema": {
        "fields": [
            {"name": "title", "type": "string", "required": True},
            {"name": "department", "type": "string"},
            {"name": "location", "type": "string"},
            {"name": "headcount", "type": "number", "required": True},
            {"name": "priority_score", "type": "number"},  # 0-100 for drag-drop ordering
            {"name": "target_close_date", "type": "string", "format": "date"},
            {"name": "status", "type": "string"},  # OPEN, FILLED, CANCELLED
            {"name": "hiring_manager", "type": "string"},
            {"name": "description", "type": "string"},
            {"name": "notes", "type": "string"},
        ]
    },
    "allowed_relations": [
        {"target_type": "Job", "relation_name": "jobs", "cardinality": "one_to_many"}
    ],
    "features": {"has_lifecycle": False, "has_projection": False, "has_form": True},
    "icon": "clipboard-list",
    "color": "#F59E0B",  # Amber
}
```

**Update Job entity type** - Add `priority_score` field:
```python
{"name": "priority_score", "type": "number"},  # Inherited from Requisition
{"name": "requisition_id", "type": "string"},  # Reference to parent Requisition
```

**Tasks**:
- [ ] Add Requisition to `ATS_ENTITY_TYPES` list
- [ ] Add `priority_score` and `requisition_id` fields to Job entity type schema
- [ ] Update seed function to include new fields
- [ ] Verify entity type seeding on startup

---

#### Phase 2: Backend - Priority Cascade Service ✅ COMPLETE

**New service function** (`services/entity_service.py` or new `requisition_service.py`):

```python
def cascade_requisition_priority(
    db: Session,
    org_id: str,
    requisition_id: str,
    new_priority_score: int
) -> list[str]:
    """
    Update priority_score on all Jobs linked to a Requisition.
    Returns list of updated Job IDs.
    """
    # 1. Find all Job entities related to this Requisition
    # 2. Update each Job's data.priority_score
    # 3. Emit events for audit trail
    # 4. Return updated Job IDs
```

**API endpoint** (`api/routes/entities.py` or new `requisitions.py`):
- `PATCH /entities/{requisition_id}/priority` - Update priority and cascade to jobs
- Request: `{"priority_score": 85}`
- Response: `{"updated_job_ids": ["job-1", "job-2"]}`

**Bulk reorder endpoint**:
- `POST /entities/reorder` - Batch update priority_score for multiple entities
- Request: `{"entity_ids": ["req-1", "req-2", "req-3"], "entity_type": "Requisition"}`
- Response: Assigns scores 100, 66, 33 based on position

**Tasks**:
- [ ] Create `cascade_requisition_priority()` function
- [ ] Add `PATCH /entities/{id}/priority` endpoint
- [ ] Add `POST /entities/reorder` bulk endpoint
- [ ] Add tests for priority cascade logic
- [ ] Add tests for bulk reorder endpoint

---

#### Phase 3: Migration ✅ COMPLETE (No migration needed)

**Migration 031: No schema changes needed**

The Requisition entity type uses the existing `entities` table with JSON `data` field. No new database tables or columns required.

However, if existing Jobs need `priority_score` backfilled:

```python
"""Add priority_score to existing jobs.

Revision ID: 031
Revises: 030
"""

def upgrade() -> None:
    # Backfill existing Jobs with default priority_score
    # This is a data migration, not schema migration
    op.execute("""
        UPDATE entities
        SET data = jsonb_set(COALESCE(data, '{}')::jsonb, '{priority_score}', '50')
        WHERE entity_type = 'Job'
        AND (data->>'priority_score') IS NULL
    """)

def downgrade() -> None:
    # Remove priority_score from Jobs (optional)
    pass
```

**Tasks**:
- [ ] Create migration 031 for data backfill (if needed)
- [ ] Test migration upgrade and downgrade
- [ ] Verify idempotency (safe to run multiple times)

---

#### Phase 4: Frontend - Types & API ✅ COMPLETE

**New types** (`frontend/src/domains/ats/types/requisition.ts`):

```typescript
export interface Requisition {
  entity_id: string;
  entity_type: 'Requisition';
  data: {
    title: string;
    department?: string;
    location?: string;
    headcount: number;
    priority_score: number;
    target_close_date?: string;
    status: 'OPEN' | 'FILLED' | 'CANCELLED';
    hiring_manager?: string;
    description?: string;
    notes?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface RequisitionWithJobs extends Requisition {
  jobs: Job[];
  application_count: number;
}
```

**API methods** (`frontend/src/domains/ats/services/api.ts`):
- `getRequisitions()` - List all requisitions
- `getRequisition(id)` - Get single requisition with linked jobs
- `createRequisition(data)` - Create new requisition
- `updateRequisition(id, data)` - Update requisition
- `updateRequisitionPriority(id, score)` - Update priority (cascades to jobs)
- `reorderRequisitions(ids)` - Bulk reorder by position

**Tasks**:
- [ ] Create `requisition.ts` types file
- [ ] Add API methods to api.ts
- [ ] Export from domains/ats/index.ts

---

#### Phase 5: Frontend - Requisitions Page ✅ COMPLETE

**New page** (`frontend/src/domains/ats/pages/RequisitionsPage.tsx`):

**Features**:
- Sortable list view with drag-and-drop reordering (@dnd-kit)
- Priority column with drag handle
- Status badges (OPEN=green, FILLED=blue, CANCELLED=gray)
- Target close date with overdue highlighting
- Headcount vs filled positions display
- Linked jobs count with expandable list
- Create/Edit modal
- Filter by status, department

**Components**:
- `RequisitionList` - Main sortable list
- `RequisitionRow` - Individual row with drag handle
- `RequisitionModal` - Create/Edit form
- `RequisitionDetail` - Slide-over with full details and linked jobs

**Tasks**:
- [ ] Create RequisitionsPage with sortable list
- [ ] Implement drag-and-drop with @dnd-kit
- [ ] Create RequisitionModal for create/edit
- [ ] Add status badges and date highlighting
- [ ] Show linked jobs count
- [ ] Add navigation item to sidebar

---

#### Phase 6: Frontend - Jobs Page Priority Display ✅ COMPLETE

**Update JobsPage** (`frontend/src/domains/ats/pages/JobsPage.tsx`):

- Add priority_score column (sortable)
- Show parent Requisition link (if any)
- Visual priority indicator (high/medium/low badge or bar)
- Sort by priority by default

**Tasks**:
- [ ] Add priority column to Jobs table/grid
- [ ] Add Requisition link column
- [ ] Update default sort to priority_score desc
- [ ] Add priority filter option

---

#### Implementation Order

| Phase | Effort | Dependency | Status |
|-------|--------|------------|--------|
| Phase 1: Entity Type Definition | Small | None | ✅ Complete |
| Phase 2: Priority Cascade Service | Medium | Phase 1 | ✅ Complete |
| Phase 3: Migration | Small | Phase 1 | ✅ Complete (N/A) |
| Phase 4: Frontend Types & API | Small | Phase 2 | ✅ Complete |
| Phase 5: Requisitions Page | Large | Phase 4 | ✅ Complete |
| Phase 6: Jobs Page Updates | Medium | Phase 4 | ✅ Complete |

---

#### Files to Create/Modify

**Backend - New Files**:
| File | Purpose |
|------|---------|
| `alembic/versions/031_backfill_job_priority.py` | Data migration for existing jobs |

**Backend - Modified Files**:
| File | Change |
|------|--------|
| `services/entity_type_service.py` | Add Requisition to ATS_ENTITY_TYPES, add priority_score to Job |
| `services/entity_service.py` | Add `cascade_requisition_priority()` function |
| `api/routes/entities.py` | Add priority and reorder endpoints |

**Frontend - New Files**:
| File | Purpose |
|------|---------|
| `domains/ats/types/requisition.ts` | Requisition TypeScript types |
| `domains/ats/pages/RequisitionsPage.tsx` | Main requisitions page |
| `domains/ats/components/RequisitionList.tsx` | Sortable list component |
| `domains/ats/components/RequisitionRow.tsx` | Draggable row component |
| `domains/ats/components/RequisitionModal.tsx` | Create/Edit modal |

**Frontend - Modified Files**:
| File | Change |
|------|--------|
| `domains/ats/services/api.ts` | Add requisition API methods |
| `domains/ats/pages/JobsPage.tsx` | Add priority column and sorting |
| `layouts/AppLayout.tsx` | Add Requisitions nav item |
| `App.tsx` | Add /requisitions route |

---

### RAG Tool with Vector Database (v0.16+ Ideation)

**Goal**: Enable semantic search and analysis of documents (resumes, assignments) by embedding them in a vector database. Agents can use a `search_documents` tool to find relevant candidates based on natural language queries.

**Use Cases**:
1. **Resume Search**: "Find candidates with 5+ years of Python experience and machine learning background"
2. **Skills Matching**: "Which candidates have experience similar to the requirements in this job description?"
3. **Document Analysis**: "Summarize the key qualifications from these 10 resumes"
4. **Candidate Comparison**: "Compare the technical skills of these 3 candidates"

---

#### Architecture Overview

**Key Decision**: Leverage existing **LiteLLM** infrastructure for embeddings instead of building a separate provider system. LiteLLM already supports `litellm.embedding()` with unified interface across OpenAI, Cohere, Azure, Bedrock, Voyage, HuggingFace, etc.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Existing Infrastructure                          │
├─────────────────────────────────────────────────────────────────────┤
│  AIFeatureConfig          │  LiteLLM                                │
│  ├── feature: "embedding" │  ├── litellm.embedding(model, input)    │
│  ├── model: "text-..."    │  ├── Supports: OpenAI, Cohere, Azure,   │
│  ├── api_key_env_var      │  │   Bedrock, Voyage, HuggingFace       │
│  └── provider_config      │  └── Unified response format            │
└─────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     New RAG Components                               │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ EmbeddingConfig  │    │ ChunkingStrategy │    │ DocumentEmbed │  │
│  │ (extends AIFeat) │───▶│ (pluggable)      │───▶│ (pgvector)    │  │
│  │ - chunking opts  │    │ - fixed_size     │    │ - entity_id   │  │
│  │ - search opts    │    │ - sentence       │    │ - embedding   │  │
│  │ - dimension      │    │ - semantic       │    │ - metadata    │  │
│  └──────────────────┘    └──────────────────┘    └───────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

#### Vector Database: PGVector

**Why PGVector**: Native PostgreSQL extension, no new infrastructure, transactional consistency, familiar SQL. Already using PostgreSQL.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organizations(id),
    entity_id UUID REFERENCES entities(id) ON DELETE CASCADE,
    entity_type VARCHAR(64),
    document_type VARCHAR(32),

    embedding vector(1536),          -- Dimension from config

    chunk_index INTEGER DEFAULT 0,
    extracted_text TEXT,
    text_hash VARCHAR(64),
    metadata JSONB,
    token_count INTEGER,
    model_used VARCHAR(128),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_emb_vector ON document_embeddings
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

#### Configuration Model

Extend existing `AIFeatureConfig` pattern with embedding-specific settings in `provider_config` JSONB:

```python
# AIFeatureConfig record for embedding:
{
    "feature": "embedding",
    "model": "text-embedding-3-small",  # LiteLLM model string
    "api_key_env_var": "OPENAI_API_KEY",
    "provider_config": {
        "dimension": 1536,
        "chunking": {
            "strategy": "fixed_size",   # fixed_size, sentence, paragraph, semantic
            "chunk_size": 1000,         # tokens
            "chunk_overlap": 200
        },
        "search": {
            "default_top_k": 10,
            "min_similarity": 0.3
        },
        "auto_embed_on_upload": true
    }
}
```

---

#### Chunking Strategies

| Strategy | Description | Config Options |
|----------|-------------|----------------|
| `none` | No chunking, full document | - |
| `fixed_size` | Fixed token/char chunks | `chunk_size`, `chunk_overlap` |
| `sentence` | Split on sentence boundaries | `min_sentences`, `max_sentences` |
| `paragraph` | Split on paragraphs | `max_chunk_size` |
| `recursive` | Try separators in order | `separators[]` |

Chunking is a simple pluggable interface: `chunk(text) -> list[Chunk]`

---

#### Embedding Service (LiteLLM-based)

```python
class EmbeddingService:
    def embed(self, db, org_id, text: str) -> list[float]:
        # Get config from AIFeatureConfig
        config = get_ai_feature_config(db, org_id, feature="embedding")

        # Use LiteLLM (already integrated)
        response = litellm.embedding(
            model=config.model,  # e.g., "text-embedding-3-small"
            input=text
        )
        return response.data[0]["embedding"]

    def embed_document(self, db, org_id, entity_id, text, document_type, metadata):
        config = get_embedding_config(db, org_id)

        # 1. Chunk text using configured strategy
        chunker = get_chunker(config.chunking_strategy, config.chunking_config)
        chunks = chunker.chunk(text)

        # 2. Embed via LiteLLM
        embeddings = [self.embed(db, org_id, chunk.text) for chunk in chunks]

        # 3. Store in pgvector table
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(DocumentEmbedding(...))

    def search(self, db, org_id, query, top_k=None):
        config = get_embedding_config(db, org_id)
        query_embedding = self.embed(db, org_id, query)

        return db.execute("""
            SELECT *, 1 - (embedding <=> :query) as similarity
            FROM document_embeddings
            WHERE organization_id = :org_id
            ORDER BY embedding <=> :query
            LIMIT :top_k
        """, {...})
```

---

#### MCP Tool: `search_documents`

```python
@mcp_server.tool()
async def search_documents(
    query: str,
    document_type: str = None,
    top_k: int = 5
) -> dict:
    """Semantic search across documents."""
    results = embedding_service.search(db, org_id, query, top_k)
    return {
        "results": [
            {"entity_id": r.entity_id, "similarity": r.similarity, "excerpt": r.excerpt}
            for r in results
        ]
    }
```

---

#### Integration Points

| Trigger | Action |
|---------|--------|
| Resume upload confirmed | Auto-embed if `auto_embed_on_upload=True` |
| Document uploaded | Auto-embed based on document type config |
| Entity deleted | Cascade delete embeddings |
| Config model changed | Option to re-embed existing documents |

---

#### Settings UI

Add to **Settings > Integrations** or **Settings > AI Features**:

```
┌─────────────────────────────────────────────────────────────┐
│ Document Search (RAG)                              [Enabled]│
├─────────────────────────────────────────────────────────────┤
│ Embedding Model: [text-embedding-3-small ▼]                 │
│                  (Uses your configured OpenAI API key)      │
│                                                             │
│ Chunking Strategy: [Fixed Size ▼]                           │
│   Chunk Size: [1000] tokens                                 │
│   Overlap:    [200] tokens                                  │
│                                                             │
│ Search Defaults:                                            │
│   Results per query: [10]                                   │
│   Min similarity:    [0.3]                                  │
│                                                             │
│ [x] Auto-embed resumes on upload                            │
│ [ ] Auto-embed all documents                                │
│                                                             │
│ [Test Configuration]  [Re-embed All Documents]              │
└─────────────────────────────────────────────────────────────┘
```

---

#### Implementation Phases

| Phase | Scope | Effort | Status |
|-------|-------|--------|--------|
| **1** | EmbeddingConfig in AIFeatureConfig + migration + pgvector setup | Small | ❌ Not Started |
| **2** | EmbeddingService with LiteLLM + fixed_size chunking | Medium | ❌ Not Started |
| **3** | Resume upload integration (auto-embed) | Small | ❌ Not Started |
| **4** | `search_documents` MCP tool | Small | ❌ Not Started |
| **5** | Settings UI for configuration | Medium | ❌ Not Started |
| **6** | Additional chunking strategies (sentence, semantic) | Small | ❌ Not Started |

---

#### Cost Considerations

- **OpenAI text-embedding-3-small**: $0.02 per 1M tokens (~$0.00002 per resume)
- **Storage**: ~6KB per embedding (1536 * 4 bytes)
- **At 10,000 resumes**: ~$0.20 embedding cost, ~60MB storage

---

#### Key Simplifications

1. **No new provider abstraction** - LiteLLM handles all providers via unified API
2. **Reuse AIFeatureConfig pattern** - Consistent with existing LLM model configuration
3. **Single vector column** - Start simple, handle dimension changes via re-embedding
4. **Chunking is pluggable** - Easy to add new strategies without changing core
5. **Config in JSONB** - Flexible, no migrations for new config options

---

### Role-Based Access Control (RBAC) with Field Permissions (v0.17 Planned)

**Goal**: Implement a fully configurable RBAC system where admins can create custom roles, define entity-level permissions, and configure field-level visibility/editability per role.

**Use Cases**:
1. **Custom Roles**: Create "External Reviewer" role with read-only access to candidates
2. **Field Protection**: Hide salary fields from hiring managers, show only to recruiters/admins
3. **Resource Scoping**: Limit hiring managers to only see applications for their assigned jobs
4. **PII Masking**: Mask phone/email for viewer role, show "****" instead

---

#### Current State

**What Exists**:
- 4 static roles: `admin`, `recruiter`, `hiring_manager`, `viewer`
- Route-level protection via `require_admin`, `require_recruiter_or_admin`, etc.
- Multi-org support with per-org role assignment
- JWT authentication with role in token

**What's Missing**:
- Custom role creation
- Entity-type scoped permissions (`Candidate.read`, `Job.write`)
- Field-level permissions (view/edit/mask per field per role)
- Resource scoping (user → specific jobs)
- Dynamic permission checks

---

#### Data Model

```
┌─────────────────────┐
│       roles         │
├─────────────────────┤
│ id                  │
│ organization_id     │
│ name (unique/org)   │  ← "external_reviewer"
│ display_name        │  ← "External Reviewer"
│ description         │
│ is_system           │  ← Built-in roles can't be deleted
│ priority            │  ← For hierarchy (higher = more access)
│ color               │  ← For UI badges
│ created_at          │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐      ┌─────────────────────┐
│  role_permissions   │      │  field_permissions  │
├─────────────────────┤      ├─────────────────────┤
│ id                  │      │ id                  │
│ role_id             │      │ organization_id     │
│ entity_type         │      │ entity_type         │
│ action              │      │ field_name          │
│   (create/read/     │      │ role_id             │
│    update/delete/   │      │ can_view            │
│    transition)      │      │ can_edit            │
│ allowed (bool)      │      │ mask_value          │  ← "****" or "Confidential"
└─────────────────────┘      └─────────────────────┘
          │
          ▼
┌─────────────────────┐
│  user_roles         │  ← Replaces User.role single field
├─────────────────────┤
│ user_id             │
│ organization_id     │
│ role_id             │
│ resource_type       │  ← Optional: "Job", null (all)
│ resource_id         │  ← Optional: specific job ID
└─────────────────────┘
```

---

#### Permission Service

```python
class PermissionService:
    def can(self, user_id, org_id, entity_type, action) -> bool:
        """Check if user can perform action on entity type."""
        roles = get_user_roles(user_id, org_id)
        for role in roles:
            perm = get_role_permission(role.id, entity_type, action)
            if perm and perm.allowed:
                return True
        return False

    def filter_entity_response(self, user_id, org_id, entity) -> dict:
        """Remove/mask fields user can't see."""
        visible = self.get_visible_fields(user_id, org_id, entity.entity_type)
        masked = self.get_masked_fields(user_id, org_id, entity.entity_type)

        filtered_data = {}
        for field, value in entity.data.items():
            if field in visible:
                filtered_data[field] = value
            elif field in masked:
                filtered_data[field] = masked[field].mask_value
            # else: field is hidden entirely

        return filtered_data
```

---

#### API Dependency

```python
def require_permission(entity_type: str, action: str):
    """Dependency factory for permission checks."""
    def checker(user = Depends(get_current_user), org_id = Depends(get_org_id)):
        if not permission_service.can(user.id, org_id, entity_type, action):
            raise HTTPException(403, f"No permission: {entity_type}.{action}")
        return user
    return checker

# Usage:
@router.post("/entities")
def create_entity(
    payload: EntityCreate,
    user = Depends(require_permission("ATS.Candidate", "create"))
):
    ...
```

---

#### Default System Roles

Seeded on org creation (`is_system=True`):

| Role | Priority | Default Entity Permissions | Field Access |
|------|----------|---------------------------|--------------|
| `admin` | 100 | All actions on all types | All fields |
| `recruiter` | 70 | CRUD Candidate/Application, Read Job | All except compensation |
| `hiring_manager` | 50 | Read all, Transition Applications | No salary/PII |
| `viewer` | 10 | Read only | Public fields only |

---

#### API Endpoints

```
# Roles
GET    /config/roles                    # List roles for org
POST   /config/roles                    # Create custom role
GET    /config/roles/{id}               # Get role with permissions
PUT    /config/roles/{id}               # Update role
DELETE /config/roles/{id}               # Delete custom role (not system)

# Role Permissions (entity-level)
PUT    /config/roles/{id}/permissions   # Bulk update entity permissions
GET    /config/roles/{id}/permissions   # Get all permissions for role

# Field Permissions
GET    /config/field-permissions/{entity_type}         # Get field perms matrix
PUT    /config/field-permissions/{entity_type}/{role}  # Update field perms

# User Role Assignment
GET    /users/{id}/roles                # Get user's roles
PUT    /users/{id}/roles                # Assign roles to user
```

---

#### Implementation Phases

| Phase | Scope | Effort | Status |
|-------|-------|--------|--------|
| **1** | Database models + migrations (Role, RolePermission, FieldPermission, UserRole) | Medium | ❌ Not Started |
| **2** | PermissionService with entity-level checks | Medium | ❌ Not Started |
| **3** | Migrate existing User.role to UserRole table | Small | ❌ Not Started |
| **4** | API dependency `require_permission()` + update routes | Medium | ❌ Not Started |
| **5** | Response filtering for field permissions | Medium | ❌ Not Started |
| **6** | Seed default system roles on org creation | Small | ❌ Not Started |
| **7** | API endpoints for role/permission CRUD | Medium | ❌ Not Started |
| **8** | Settings UI: Roles list + Role editor modal | Large | ❌ Not Started |
| **9** | Settings UI: Field permissions matrix | Medium | ❌ Not Started |
| **10** | Update Users tab to assign roles from new system | Small | ❌ Not Started |

---

#### Files to Create

| File | Purpose |
|------|---------|
| `models/rbac.py` | Role, RolePermission, FieldPermission, UserRole models |
| `services/permission_service.py` | Permission checking and response filtering |
| `api/routes/roles.py` | Role CRUD endpoints |
| `api/routes/permissions.py` | Permission management endpoints |
| `schemas/rbac.py` | Pydantic schemas for RBAC |
| `alembic/versions/033_add_rbac_tables.py` | Migration for RBAC tables |

#### Files to Modify

| File | Change |
|------|--------|
| `api/deps.py` | Add `require_permission()` dependency |
| `api/routes/entities.py` | Use new permission checks |
| `api/routes/transitions.py` | Use new permission checks |
| `services/entity_service.py` | Add response filtering hook |
| `models/user.py` | Deprecate `role` field in favor of UserRole |

---

#### Phase 5: Templates ❌ NOT STARTED

**Goal**: Package ATS configuration as importable template

**Status**: Not started
- Depends on all previous phases being complete
- Would allow new domains (PMO, CRM) to be created without code changes

**Template Structure** (`templates/ats_starter.py`):
```python
ATS_TEMPLATE = {
    "name": "ATS Starter",
    "description": "Applicant Tracking System with candidates, jobs, and applications",
    "version": "1.0",
    "entity_types": [CANDIDATE_TYPE, JOB_TYPE, APPLICATION_TYPE],
    "state_machines": [APPLICATION_WORKFLOW],
    "extraction_configs": [RESUME_EXTRACTOR],
    "view_definitions": [APPLICATION_PIPELINE_VIEW, SLA_HEATMAP_VIEW],
    "picklists": [DEPARTMENTS, LOCATIONS, SOURCES],
    "form_schemas": [CANDIDATE_FORM, JOB_FORM, APPLICATION_FORM],
}
```

**Template Installer**:
```python
def install_template(db, org_id, template_name):
    """Install a template for an organization."""
    template = load_template(template_name)
    for entity_type in template["entity_types"]:
        entity_type_service.create_entity_type(db, org_id, entity_type)
    # ... etc for all config types
```

**API**:
- `GET /templates` - List available templates
- `POST /templates/{name}/install` - Install template for org

---

#### Implementation Order

| Phase | Effort | Dependency | Status |
|-------|--------|------------|--------|
| **Phase 1**: Entity Type Registry | Medium | None | ✅ Complete |
| **Phase 2**: Extraction Configs | Medium | Phase 1 (uses entity types) | ✅ Complete |
| **Phase 3**: View Definitions | Large | Phase 1 (uses entity types) | ✅ Complete |
| **Phase 4**: Action Library | Medium | Phase 2 (used by extraction) | ⚫ Superseded (use agents instead) |
| **Unified Agent Architecture** | Medium | None | ✅ Complete |
| **Phase 5**: Templates | Small | All above | ❌ Not Started |

---

#### Success Criteria

After all phases:
1. Zero hardcoded `"ATS.*"` strings in platform code
2. New domain (e.g., PMO) can be created via API/seed without any Python changes
3. Existing ATS functionality works identically via template
4. All extraction prompts/schemas editable via API
5. Views/projections configurable per entity type

---

### Legacy Refactoring Tasks (Superseded by Configuration-Driven Architecture)

The following tasks are superseded by the Airtable Model refactoring above:

- [ ] ~~**Split Resume Parser into Generic + Domain-Specific**~~ → Phase 2: Extraction Configs
- [ ] ~~**Move ATS Projections to Domain Pack**~~ → Phase 3: View Definitions
- [ ] ~~**Remove Hardcoded ATS Entity Type Checks**~~ → Phase 1: Entity Type Registry
- [ ] **Frontend: Fix Core → Domain Imports**:
    - `core/types/index.ts` imports from `domains/ats/types/stageComment` - move types to core.
    - `core/services/api.ts` imports from `domains/ats/types/resumeUpload` - move resume API to domain.
