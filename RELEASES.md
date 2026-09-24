# Releases

## v0.17.0 (7 February 2026)

### Features

**Transition Dialog with Preflight Guards (SWARM-03)**
- Clicking a transition button now opens a dialog instead of firing the transition immediately
- New `GET /entities/{id}/transitions/{trigger}/preflight` endpoint evaluates guards without executing, returning required fields, prime fields, comment config, and guard status
- Dialog renders mandatory fields (from `FIELD_PRESENT` guards), prime fields (configurable per-transition), and comment textarea
- Submit flow: update entity fields → add comment → execute transition in one action
- Kanban drag-and-drop also opens the transition dialog instead of firing directly
- Funnel Builder: transitions are now expandable with prime fields config using a field selector dropdown grouped by native and referenced fields
- Fixed double-execution bug where `onTransitionComplete` re-executed the transition after dialog submit

**Job Description Upload & AI Extraction (SWARM-04)**
- Upload PDF, DOCX, or TXT job descriptions to Job entities via a dedicated "Job Description" section
- New `jd` document type with upload context for `ATS.Job`, agent-enabled with JD-specific extraction prompt
- System agent `jd_extraction_agent` extracts skills, experience level, responsibilities, and qualifications into job fields via `update_entity` tool
- Text paste saves directly to `data.description` on the Job entity (no document created)
- Migration `043`: provisions JD doc type and agent to all existing tenants (idempotent)

**Interview Transcription (Work in Progress)**
- Real-time interview transcription with ElevenLabs and OpenAI Whisper provider support — not yet fully functional
- New `transcription_sessions` and `transcription_segments` tables for storing transcription data
- Transcription provider configuration UI in Settings > Integrations with API key management and model selection
- Standalone transcription bot service for automated session capture
- Migrations `039`, `040`, `041` for transcription tables, config, and OpenAI provider

**Inbound Email Forwarding (SWARM-02)**
- Forward emails to `intake-{org-slug}@ats.newtuple.com` for automatic candidate processing
- Parses email content (HTML→text), sender info, subject, and attachments using Python stdlib `email` + BeautifulSoup
- Auto-matches sender email to existing candidates; creates new candidates if no match
- Resume PDF attachments processed through existing `resume_upload_service` pipeline
- Email threads stored as `email_thread` document type on the entity
- New `inbound_emails` tracking table (migration `042`) and SNS webhook endpoint
- AWS SES infrastructure documented in deployment guide

**Resume Upload Performance (SWARM-05)**
- Resume extraction optimized from ~2 minutes toward under 15 seconds target
- Pre-injects form schema and document text into agent system prompt, reducing LLM round-trips from 3-4 to 1-2
- Form schema cached per `(entity_type, org_id)` across batch extractions
- `MAX_CONCURRENT_EXTRACTIONS` increased from 4 to 8
- Per-stage timing instrumentation logs added for performance monitoring

### Security Fixes

**Multi-Tenancy Data Leak Fix (SWARM-06)**
- Fixed 22+ database queries across 12 files that lacked `organization_id` filtering
- Prevents cross-tenant data access in documents, comments, events, guards, duplicate detection, and entity projections
- Added `org_id` parameter to functions where it was missing: `candidate_service` (3 functions), `event_service` (2), `projection_service` (2)
- Added org_id filter to functions where parameter existed but was unused: `document_service` (7 functions), `guard_service` (3), `action_executor`, `comments` route, `resume_upload` route
- Route layer fixes: `documents.py` routes now pass org_id to service functions, `events.py` passes org_id to `list_events()`
- `transition_service.py` passes `entity.organization_id` to `find_event_by_idempotency()` for idempotency checks

### Technical Details
- 5 new database migrations (039–043)
- New models: `TranscriptionSession`, `TranscriptionSegment`, `TranscriptionConfig`, `InboundEmail`
- New services: `inbound_email_service`, `transcription_service`, `transcription_config_service`
- New frontend components: `TransitionDialog`, `JobDescriptionSection`
- New backend endpoints: preflight transition, inbound email webhook, transcription CRUD, downloads
- New schemas: `PreflightResponse`, `PreflightFieldRequirement`, `PreflightCommentConfig`
- Chrome extension for ATS browser integration

---

## v0.16.0 (February 2026)

### Features

**Team Invitations & Onboarding**
- Admins can invite teammates directly from Settings > Users with role selection (Admin, Recruiter, Hiring Manager)
- Secure token-based invite links with 7-day expiry — new users accept via a dedicated `/accept-invite` page
- Accepted invitations auto-activate the user account and assign the correct organization and role
- Admins can resend (regenerates token and extends expiry) or revoke pending invitations
- New `invitations` table with status lifecycle: pending → accepted / expired / revoked
- Backend: full invitation service with create, validate, accept, resend, revoke endpoints
- Frontend: `InviteUserDialog` component and updated `UsersTab` showing pending invitations alongside active users

**Agent Tracing & Observability**
- New admin-only Agent Traces tab in Settings for inspecting AI agent execution runs
- Each trace captures: agent name, run type (persistent/ephemeral), model used, status, token usage, duration, and iteration count
- Timeline-style event viewer with progressive disclosure — expand a run to see individual events (system prompt, user message, assistant response, tool calls, tool results)
- Events are color-coded by kind with searchable, filterable run history
- Traces auto-expire after a configurable TTL (default 30 days) with best-effort cleanup
- Backend: `AgentTraceRun` and `AgentTraceEvent` models, `AgentTraceService` with async persistence via thread pool, migration 038
- Frontend: `AgentTracesTab` component with run list, detail expansion, duration/token formatting

**Tenant Provisioning**
- New automatic provisioning service creates all default resources when an organization is created
- Provisions: entity types (Candidate, Job, Application, Requisition), picklists (department, location, candidate_source, etc.), form schemas, document type configs (with resume extraction prompt), a standard 7-stage ATS funnel, view definitions, agent definitions, and RBAC roles
- Idempotent — safe to run multiple times without creating duplicates or overwriting customizations
- API endpoints: `POST /organizations/{id}/provision` and `GET /organizations/{id}/provision-status`
- Optional `create_sample_job` parameter to seed a sample job posting for new tenants
- Backend: 544-line `tenant_provisioning_service.py` with comprehensive test suite (25 tests)

**Async Resume Upload with Progress Tracking**
- Resume uploads now use presigned URLs for direct-to-MinIO uploads, bypassing the backend for file transfer
- Upload modal closes immediately — progress is tracked in a new floating `UploadProgressPanel` in the bottom-right corner
- Per-file progress bars with overall percentage, cancel support, and error reporting
- Backend: new presigned URL endpoints (`prepare-upload`, `upload-file`, `complete-upload`) and parallel LLM extraction via `asyncio.to_thread`
- Frontend: new `uploadService` singleton managing upload sessions with `XMLHttpRequest` progress events, and `UploadProgressPanel` component

**Configurable Agent Models & Tools**
- Document types now support selecting which LLM model to use for agent processing (e.g., GPT-4o, Claude Sonnet)
- Model selector dropdown in both Document Types settings (agent processing section) and Agents settings (agent editor modal)
- Available models are fetched from `/api/config/ai-features/models`, filtered by which API keys are configured
- Agent tools are now read from `DocumentTypeConfig.agent_tools` instead of being hardcoded — `extract_only()` respects configured tools while filtering out `update_entity` to prevent side effects
- Backend: new `agent_model` column on `DocumentTypeConfig`, migrations 035 (agent_system_prompt) and 036 (agent_model)

**Improved Resume Extraction Accuracy**
- Added `skills`, `experience`, `education`, and `summary` fields to the default ATS.Candidate form schema so agents know these should be arrays
- New `JSON_ARRAY` field type with `is_array` and `item_schema` hints returned by `get_form_schema`
- Agent system prompt restructured with explicit numbered steps — emphasizes using `get_form_schema` (not `get_entity`) to avoid LLM confusion
- Added `normalize_extracted_data()` as defense-in-depth to coerce comma-separated strings into arrays when the schema expects them
- Fixes Pydantic validation errors where skills were returned as `"Python, JavaScript"` instead of `["Python", "JavaScript"]`

**Superadmin Role & RBAC Hardening**
- New `SUPERADMIN` role separate from `ADMIN` — superadmins retain their role when switching between organizations
- All admin-only endpoints (user management, invitations, agent traces, settings) now accept both `SUPERADMIN` and `ADMIN` roles
- Backend: `SUPERADMIN` added to `UserRole` enum, `require_admin` and `require_superadmin` dependencies updated, all user and invitation route guards updated
- Frontend: `superadmin` added to `UserRole` type, settings/traces visibility and protected routes updated

**Smart Registration & Auto-Org Assignment**
- Users are automatically assigned to organizations based on email domain during registration
- Company domains (e.g., `acme.com`) auto-create a pending organization named from the domain
- Public email domains (gmail, outlook, yahoo, etc.) require an explicit organization name — a contextual input field appears automatically when a public domain is detected
- Three approval paths: ACTIVE (first user in an active org gets auto-approved as admin), PENDING_ORG_ADMIN (joining an existing org, awaits org admin approval), PENDING_PLATFORM (new org created, awaits super-admin approval)
- Google OAuth follows the same logic — new Google users get the same org assignment and approval flow
- `approve_organization()` now activates all pending users in the org, not just the requester
- Backend: new `ApprovalType` enum, `UserCreationResult` dataclass, `get_or_create_organization_for_email()`, `is_public_email_domain()`. `/register` returns 201 (active) or 202 (pending) with `RegistrationResponse`. `/register-with-org` deprecated
- Frontend: `RegistrationPendingError` for 202 handling. Login page replaces the separate "Create Organization" mode with inline org-name field. `PendingApprovalPage` shows contextual messaging with "what happens next" steps for new org requests

**Platform Admin User Management**
- Super-admins can view, create, and delete users in any organization from the Organizations settings tab
- Organizations tab expanded with "Pending" and "All" sub-tabs, expandable org rows showing user lists with role badges
- Inline add-user form with role selector and user deletion with confirmation dialog
- Backend: new endpoints `GET/POST/DELETE /organizations/{org_id}/users` (super-admin only)
- Frontend: `OrganizationsTab` rewritten with user management UI, `organizations.listUsers/createUser/deleteUser` API methods

### Bug Fixes
- Fixed `organization_id` not being set in `create_relation()`, `create_playbook()`, `PlaybookRun`, and `PlaybookStepRun` — caused cross-tenant data leaks
- Fixed Alembic migration 034 revision IDs (`034_picklist_composite_pk` → `034`) to match project convention, which was breaking the migration chain with `KeyError`
- Fixed 42 previously failing tests by adding `organization_id` to test helpers in `test_guard_service.py` and `org_id` to all `PlaybookStartContext` calls

### Technical Details
- 6 new database migrations (034–038 + 037 for invitations)
- New models: `Invitation`, `AgentTraceRun`, `AgentTraceEvent`
- New services: `invitation_service`, `agent_trace_service`, `tenant_provisioning_service`, `uploadService` (frontend)
- New frontend pages: `AcceptInvitePage`
- New frontend components: `InviteUserDialog`, `AgentTracesTab`, `UploadProgressPanel`
- `DocumentAgentExecutor.extract_only()` is now async (uses `await asyncio.to_thread`)
- Composite primary key `(id, organization_id)` added to picklists table (migration 034)
- `SUPERADMIN` role added to `UserRole` enum (backend + frontend)
- `ApprovalType` enum and `UserCreationResult` dataclass added to auth service
- `get_or_create_organization_for_email()` and `is_public_email_domain()` added to organization service
- Platform admin user management endpoints added to organizations router

---

## v0.15.0 (January 2026)

### Features

**Team Interest (Candidate Likes)**
- Like candidates to express team interest and facilitate collaboration
- Avatar stack on Kanban application cards shows who liked each candidate
- Team Interest section in candidate detail panel with full user list
- Like/unlike toggle button with real-time updates
- Bulk fetch API for efficient Kanban board loading

### Technical Details
- New `candidate_likes` database table with organization scoping
- Idempotent like/unlike operations prevent duplicates
- Denormalized user info for efficient avatar display
- Bulk fetch endpoint avoids N+1 queries on pipeline board

---

## v0.14.0 (January 2026)

### Features

**Requisition Management**
- New Requisitions page for managing job requisition requests
- Create requisitions with title, department, location, headcount, and target close date
- Link existing jobs to requisitions during creation or editing
- Priority-based job ordering - priority cascades from requisition to linked jobs
- Status tracking: Open, Filled, Cancelled

**Document Type Configuration**
- Resume extraction prompt now editable in Settings > Documents tab
- System document types (resume) marked with badge and protected from deletion
- Added `is_system` flag to DocumentTypeConfig model

**Schema-Aware Agent Extraction**
- New `get_form_schema` tool allows agents to discover entity field definitions
- New `search_entities` tool for finding candidates by skills, jobs by requirements, etc.
- Document agent automatically extracts data matching the entity's form schema
- No need to specify extraction schema in prompts - agent learns from FormSchema
- Agent-based extraction enabled via "Agent Processing" toggle on document types

**Reference Fields**
- New `reference` field type for displaying fields from related entities
- "Add from Related Entity" button in Application form config
- Select candidate fields (e.g., notice_period, linkedin_url) to show on applications
- Dynamic rendering - custom candidate fields appear automatically when configured

### Bug Fixes
- Fixed pipeline funnels dropdown menu disappearing too quickly (converted to click-based)
- Fixed allowed extensions input field not accepting values after comma
- Fixed job linking during requisition creation (was only working on edit)
- Fixed requisition drag-and-drop reordering not working (entity type mismatch)

### Improvements
- Navigation order updated: Dashboard, Pipelines, Candidates, Jobs, Requisitions
- Removed AI Feature Settings from Integrations tab (moved to Documents tab)
- Entity type references standardized to `ATS.Job` and `ATS.Requisition` format

---

## v0.13.0 (January 2026)

### Features

**Database Infrastructure**
- PostgreSQL is now required for all environments
- Improved database connection pooling for better performance
- Fixed database schema circular dependency issues

**Resume Upload Reliability**
- Resume files now reliably link to candidates even if jobs are deleted
- Storage keys preserved in extraction results for robustness
- Improved error handling and logging for upload issues

**Platform Stability**
- Fixed multi-tenant organization isolation in all services
- Improved test coverage with 297 passing tests
- AI agent tools now properly scoped to organization

---

## v0.12.0 (January 2026)

### Features

**Calendar Integration & Interview Scheduling**
- Schedule interviews directly from application detail view
- Google Calendar OAuth integration for seamless calendar access
- ICS email fallback for users without Google Calendar connected
- Auto-populated interview details with candidate and job information

**Bulk Resume Import Enhancements**
- Select a job when importing resumes to automatically create applications
- Concurrent processing - up to 4 resumes processed simultaneously
- 60-second timeout per file to prevent indefinite hangs
- Real-time incremental progress updates during extraction

**Multi-Organization Membership**
- Users can now belong to multiple organizations
- Organization switcher in header for multi-org users
- Self-service organization registration with approval workflow
- Super-admin panel for managing organization approvals

**Background Job Management**
- View processing jobs in Settings > Background Jobs
- Delete stuck, queued, or failed jobs directly from UI
- Clear job queue without database access

### Bug Fixes
- Fixed "Unknown Position" showing on applications created via bulk import
- Fixed resume processing getting stuck at 0% progress
- Fixed notification navigation for application and settings links

---

## v0.11.0 (January 2026)

First public release of the Newtuple ATS Platform.

### Features

**AI Assistant**
- AI-powered sidecar accessible from any page
- Natural language queries about candidates and applications
- Automated playbooks with AI tools

**Comments & Notifications**
- Add comments to applications, grouped by pipeline stage
- @mention teammates to notify them via email

**Document Processing**
- Drag-and-drop resume upload
- AI extracts skills, experience, and education automatically
- PDF preview in candidate detail view

**Team Management**
- Admin approval workflow for new users
- Role-based access (Admin, Recruiter, Hiring Manager)
- Multi-tenant organization support

**Form Configuration**
- Reorder any field including system fields
- Custom fields appear automatically in the UI
- Configurable Comments section placement

**Mobile Experience**
- Full-screen candidate details on mobile
- Easy-access close button
- Optimized touch targets

---

## Roadmap

### v0.18.0 (Planned)

**Advanced Analytics**
- Enhanced dashboard visualizations
- Time-to-hire tracking and forecasting
- Source effectiveness analytics

**Backward Pipeline Movement (SWARM-09)**
- Move candidates backward in the hiring pipeline with comment requirements
- Loop detection and SLA timer reset on backward movement

**Bulk CSV Import (SWARM-01)**
- Import candidates and applications via CSV/Excel
- Agent-based column mapping using form schema
- Upsert by email with import report

**Rejection Email (SWARM-08)**
- User-approved rejection emails with template editor and merge fields
- Email preview and confirmation before sending

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 0.17.0 | 7 Feb 2026 | Transition dialog, JD upload, interview transcription (WIP), inbound email, resume performance, multi-tenancy security fix |
| 0.16.0 | Feb 2026 | Superadmin role, smart registration, platform user management, invitations, agent tracing, tenant provisioning, async uploads |
| 0.15.0 | Jan 2026 | Team Interest (candidate likes), avatar stacks on Kanban cards |
| 0.14.0 | Jan 2026 | Requisition management, document type configuration, UI fixes |
| 0.13.0 | Jan 2026 | PostgreSQL-only, resume upload reliability, platform stability |
| 0.12.0 | Jan 2026 | Calendar integration, bulk import with auto-applications, multi-org membership |
| 0.11.0 | Jan 2026 | Initial release with AI assistant, comments, document processing |
