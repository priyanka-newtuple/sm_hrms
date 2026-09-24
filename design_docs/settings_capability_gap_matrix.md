# Settings Capability Gap Matrix

Date: 2026-03-20

Scope:
- Frontend scope is the replicated settings-only harness under `/Users/dhiraj/github/ai_ats/modular_frontend/src/domains/ats`.
- Backend scope is the currently running modular backend OpenAPI served from `http://127.0.0.1:8002/openapi.json`.
- Goal is roadmap benchmarking first: identify every backend capability the current settings frontend needs, then map the frontend API surface against what modular backend actually exposes today.

## Executive Summary

The settings UI currently depends on 18 service groups and 116 endpoint-method shapes. Those endpoints assume the legacy ATS API contract: mostly root-level resources such as `/config/*`, `/users`, `/roles`, `/organizations`, `/agent/*`, `/playbooks/*`, and `/state-machines`.

The modular backend now provides exact or near-exact generic coverage for a subset of the settings API surface:
- state machine registry and version inspection
- agent definitions and runtime admin
- agent trace run listing and detail inspection

It also exposes adjacent capabilities in a few other domains:
- forms and metadata registry
- pipeline and lifecycle projections
- task APIs
- integrations and integrations calendar
- document upload and retrieval
- communication email config

Those adjacent capabilities are not drop-in replacements for the current frontend contract. The current product implication is:
- If the existing settings UI must remain functionally intact, the missing capability domains need to be added or adapted explicitly.
- Rationalization should happen after this matrix, not before, so functionality is not lost accidentally.

## Capability Benchmark

For the settings frontend to work properly without reducing functionality, the backend needs these capability domains:

| Domain | Capability Required By UI | Current Modular Status |
| --- | --- | --- |
| State machine registry | List and inspect versioned workflow/state machine definitions | Exact coverage for current UI needs |
| Funnel management | CRUD, version history, validation, publish workflow for funnels | Partial-adjacent only |
| Form configuration | List, create, update, reset per-entity form schemas; seed defaults | Partial-adjacent only |
| Picklist management | CRUD picklists used by forms | Missing |
| User integrations | List user integrations, OAuth URL/callback, disconnect | Partial-adjacent only |
| User admin | User listing, status transitions, role assignment, summary stats | Missing |
| Invitations | Create, validate, accept, resend, revoke org invitations | Missing |
| Organization admin | Org listing, approval, deletion, per-org user management | Missing |
| RBAC roles | Role CRUD, duplicate, user-role assignment, permission summary | Missing |
| Document type config | CRUD document types plus extraction tools and presets | Missing |
| Processing jobs | List, inspect, delete background jobs, fetch active job | Partial-adjacent only |
| LLM config | Provider listing, saved credentials, validate, delete | Missing |
| Email config | Provider listing, save, validate, delete, send test | Partial-adjacent only |
| Transcription config | Provider listing, save, validate, delete, list models | Missing |
| AI feature config | Feature-model mapping and available-model discovery | Missing |
| Agent definitions | Agent definition CRUD, tool manifest, sessions, actions, chat | Exact coverage for current UI contract |
| Agent traces | Run listing and run detail inspection | Exact coverage for current UI contract |
| Playbooks | Definition CRUD plus run lifecycle and step runtime actions | Missing |

## Frontend Settings API Inventory

The following inventory is taken from:
- `/Users/dhiraj/github/ai_ats/modular_frontend/src/core/services/api.ts`
- `/Users/dhiraj/github/ai_ats/modular_frontend/src/domains/ats/services/api.ts`
- usage sites under `/Users/dhiraj/github/ai_ats/modular_frontend/src/domains/ats/components/settings`

### State Machines

Required capability:
- browse versioned workflow definitions
- inspect a specific machine version

Frontend endpoints:
- `GET /state-machines`
- `GET /state-machines/{machineName}/{version}`

Settings usage:
- `SettingsPage.tsx`
- `FunnelsTab.tsx`
- `SkinContext.tsx`

Modular backend routes present:
- `GET /v1/api/state-machines`
- `GET /v1/api/state-machines/{machine_name}/{version}`
- `GET /v1/api/state-machines/{machine_name}/active`
- `POST /v1/api/state-machines`
- `POST /v1/api/state-machines/{machine_name}/{version}/activate`

Assessment:
- `exact` for the current settings UI contract
- recent workflow-foundation PRs added list and version-read semantics on the generic modular router, plus create/activate operations beyond the current UI requirement

### Funnels

Required capability:
- list funnel definitions
- fetch a funnel and its versions
- create/update funnels
- validate definitions
- publish a specific version

Frontend endpoints:
- `GET /config/funnels`
- `GET /config/funnels/{machineName}`
- `GET /config/funnels/{machineName}/versions`
- `POST /config/funnels`
- `PUT /config/funnels/{machineName}`
- `POST /config/funnels/validate`
- `POST /config/funnels/{machineName}/{version}/publish`

Settings usage:
- `FunnelsTab.tsx`

Modular backend routes present:
- `POST /v1/api/metadata_registry/funnel/resolve`
- `POST /v1/api/projections/pipeline-funnels`
- `POST /v1/api/projections/pipeline`
- `POST /v1/api/projections/pipeline/list`
- `GET /v1/api/projections/pipeline/{organization_id}/{application_id}`

Assessment:
- `missing` for CRUD, version history, validation, and publish
- `adjacent` only for read/projection and metadata resolution

### Form Schemas

Required capability:
- list form configs
- fetch one config by entity type
- create/update config
- reset config to default
- seed initial config and picklists

Frontend endpoints:
- `GET /config/forms`
- `GET /config/forms/{entityType}`
- `POST /config/forms`
- `PUT /config/forms/{entityType}`
- `POST /config/forms/{entityType}/reset`
- `POST /config/seed`

Settings usage:
- `FormConfigTab.tsx`
- `useFormSchema.ts`

Modular backend routes present:
- `POST /v1/api/forms/configs`
- `GET /v1/api/forms/configs/{organization_id}/{form_key}`
- `POST /v1/api/metadata_registry/form-configs`
- `GET /v1/api/metadata_registry/form-configs/{organization_id}/{form_key}`

Assessment:
- `partial-adjacent`
- modular backend has form config storage/read endpoints, but not the same paths, list semantics, reset flow, or seed flow

### Picklists

Required capability:
- list picklists
- fetch one picklist
- create/update/delete picklists

Frontend endpoints:
- `GET /config/picklists`
- `GET /config/picklists/{picklistId}`
- `POST /config/picklists`
- `PUT /config/picklists/{picklistId}`
- `DELETE /config/picklists/{picklistId}`

Settings usage:
- `FormConfigTab.tsx`

Modular backend routes present:
- none

Assessment:
- `missing`

### Integrations

Required capability:
- list user-connected integrations
- start Google Calendar OAuth
- complete OAuth callback
- disconnect integration

Frontend endpoints:
- `GET /integrations/me`
- `GET /integrations/google-calendar/auth-url`
- `POST /integrations/google-calendar/callback`
- `DELETE /integrations/{provider}`

Settings usage:
- `CalendarIntegrationCard.tsx`
- `GoogleCalendarCallbackPage.tsx`

Modular backend routes present:
- `GET /v1/api/integrations/accounts/{organization_id}`
- `POST /v1/api/integrations/connect`
- `GET /v1/api/integrations/events`
- `POST /v1/api/integrations/events/schedule`
- `GET /v1/api/integrations_calendar/accounts/{organization_id}`
- `POST /v1/api/integrations_calendar/connect`
- `GET /v1/api/integrations_calendar/events`
- `POST /v1/api/integrations_calendar/events/schedule`

Assessment:
- `partial-adjacent`
- modular backend has organization-scoped integration and calendar capabilities, but not the current user-scoped `/integrations/me` contract or the exact OAuth callback paths expected by the UI

### Users

Required capability:
- list users
- list pending users
- fetch a user
- approve/reject/suspend/reactivate
- update org role
- fetch aggregate stats

Frontend endpoints:
- `GET /users`
- `GET /users/pending`
- `GET /users/{userId}`
- `POST /users/{userId}/approve`
- `POST /users/{userId}/reject`
- `POST /users/{userId}/suspend`
- `POST /users/{userId}/reactivate`
- `PUT /users/{userId}/role`
- `GET /users/stats/summary`

Settings usage:
- `UsersTab.tsx`

Modular backend routes present:
- `GET /v1/api/auth/status`
- `POST /v1/api/auth/check`
- `POST /v1/api/auth/token/introspect`
- `GET /v1/api/identity_access/status`
- `POST /v1/api/identity_access/check`
- `POST /v1/api/identity_access/token/introspect`

Assessment:
- `missing`
- modular backend only exposes auth and token introspection status, not user administration

### Invitations

Required capability:
- create invitation
- list invitations
- validate token
- accept invitation
- resend invitation
- revoke invitation

Frontend endpoints:
- `POST /invitations`
- `GET /invitations`
- `GET /invitations/validate?token=...`
- `POST /invitations/accept`
- `POST /invitations/{invitationId}/resend`
- `POST /invitations/{invitationId}/revoke`

Settings usage:
- `InviteUserDialog.tsx`
- `UsersTab.tsx`
- `AcceptInvitePage.tsx`

Modular backend routes present:
- none

Assessment:
- `missing`

### Organizations

Required capability:
- list orgs and pending orgs
- get one org and current org
- approve/reject/delete org
- list per-org users
- create/delete per-org user

Frontend endpoints:
- `GET /organizations`
- `GET /organizations/pending`
- `GET /organizations/{orgId}`
- `GET /organizations/current`
- `POST /organizations/{orgId}/approve`
- `POST /organizations/{orgId}/reject`
- `DELETE /organizations/{orgId}`
- `GET /organizations/{orgId}/users`
- `POST /organizations/{orgId}/users`
- `DELETE /organizations/{orgId}/users/{userId}`

Settings usage:
- `OrganizationsTab.tsx`
- `OrgSelectorContext.tsx`

Modular backend routes present:
- `GET /v1/api/organizations/status`
- `GET /v1/api/tenants/status`

Assessment:
- `missing`

### Roles and RBAC

Required capability:
- list/get/create/update/delete roles
- duplicate a role
- fetch user roles
- set a user role
- remove a user role
- get current permission summary

Frontend endpoints:
- `GET /roles`
- `GET /roles/{roleId}`
- `POST /roles`
- `PUT /roles/{roleId}`
- `DELETE /roles/{roleId}`
- `POST /roles/{roleId}/duplicate`
- `GET /roles/users/{userId}/roles`
- `PUT /roles/users/{userId}/role`
- `DELETE /roles/users/{userId}/roles/{roleId}`
- `GET /roles/my-permissions`

Settings usage:
- `RolesTab.tsx`
- `RoleEditor.tsx`
- `useRoles.ts`
- `UsersTab.tsx`

Modular backend routes present:
- `POST /v1/api/auth/roles/grant`
- `POST /v1/api/identity_access/roles/grant`

Assessment:
- `missing`
- modular backend has a narrow grant action, not role catalog management or permission summary APIs

### Document Types

Required capability:
- list/get/create/update/delete document types
- fetch tool manifest
- fetch tool presets

Frontend endpoints:
- `GET /config/document-types`
- `GET /config/document-types/{typeId}`
- `POST /config/document-types`
- `PUT /config/document-types/{typeId}`
- `DELETE /config/document-types/{typeId}`
- `GET /config/document-types/tools`
- `GET /config/document-types/tools/presets`

Settings usage:
- `DocumentTypesTab.tsx`
- `PlaybookBuilder/StepConfigStep.tsx`

Modular backend routes present:
- `POST /v1/api/documents/upload`
- `POST /v1/api/documents/list`
- `POST /v1/api/documents/update-status`
- `GET /v1/api/documents/{organization_id}/{document_id}`
- `GET /v1/api/documents/{organization_id}/{document_id}/extraction-summary`

Assessment:
- `missing`
- modular backend supports document operations, not document type configuration

### Processing Jobs

Required capability:
- list jobs
- inspect one job
- fetch active/current job
- delete job

Frontend endpoints:
- `GET /jobs`
- `GET /jobs/{jobId}`
- `GET /jobs/active/current`
- `DELETE /jobs/{jobId}`

Settings usage:
- `ProcessingJobsTab.tsx`

Modular backend routes present:
- `POST /v1/api/background_jobs/intake-jobs`
- `GET /v1/api/background_jobs/intake-jobs/{organization_id}`
- `GET /v1/api/background_jobs/intake-jobs/{organization_id}/{job_id}`
- `POST /v1/api/intake/jobs`
- `GET /v1/api/intake/jobs/{organization_id}`
- `GET /v1/api/intake/jobs/{organization_id}/{job_id}`
- `GET /v1/api/tasks`
- `DELETE /v1/api/tasks/{task_id}`
- `PATCH /v1/api/tasks/{task_id}`

Assessment:
- `partial-adjacent`
- modular backend has intake/background job and task APIs, but not the current generic `/jobs` contract or active-job endpoint

### LLM Configuration

Required capability:
- list providers
- list configured keys
- save a key
- delete a key
- validate a key before save

Frontend endpoints:
- `GET /config/llm-keys/providers`
- `GET /config/llm-keys`
- `POST /config/llm-keys`
- `DELETE /config/llm-keys/{provider}`
- `POST /config/llm-keys/validate`

Settings usage:
- `IntegrationsTab.tsx`

Modular backend routes present:
- `GET /v1/api/llm/status`

Assessment:
- `missing`

### Email Configuration

Required capability:
- list providers
- list configured providers
- save config
- delete config
- validate credentials
- send test email

Frontend endpoints:
- `GET /config/email/providers`
- `GET /config/email`
- `POST /config/email`
- `DELETE /config/email/{provider}`
- `POST /config/email/validate`
- `POST /config/email/test`

Settings usage:
- `IntegrationsTab.tsx`

Modular backend routes present:
- `PUT /v1/api/communications/email-config`
- `GET /v1/api/communications/email-config/{organization_id}`
- `PUT /v1/api/collaboration/email-config`
- `GET /v1/api/collaboration/email-config/{organization_id}`

Assessment:
- `partial-adjacent`
- modular backend has organization-scoped email config storage, but not provider discovery, validation, delete, or test-send flows

### Transcription Configuration

Required capability:
- list providers
- list configured providers
- save config
- delete config
- validate credentials
- list available models

Frontend endpoints:
- `GET /config/transcription/providers`
- `GET /config/transcription`
- `POST /config/transcription`
- `DELETE /config/transcription/{provider}`
- `POST /config/transcription/validate`
- `POST /config/transcription/models`

Settings usage:
- `IntegrationsTab.tsx`

Modular backend routes present:
- `GET /v1/api/transcription/status`

Assessment:
- `missing`

### AI Features

Required capability:
- list AI features
- list available models
- get feature config
- update feature config
- delete feature config

Frontend endpoints:
- `GET /config/ai-features`
- `GET /config/ai-features/models`
- `GET /config/ai-features/{feature}`
- `PUT /config/ai-features/{feature}`
- `DELETE /config/ai-features/{feature}`

Settings usage:
- `AgentsTab.tsx`
- `DocumentTypesTab.tsx`

Modular backend routes present:
- none

Assessment:
- `missing`

### Agent Definitions and Runtime Admin

Required capability:
- list/get/create/update/delete agent definitions
- chat
- approve/reject pending actions
- list/get/delete sessions
- fetch tool manifest

Frontend endpoints:
- `GET /agent/definitions?active_only=...`
- `GET /agent/definitions/{definitionId}`
- `POST /agent/definitions`
- `PATCH /agent/definitions/{definitionId}`
- `DELETE /agent/definitions/{definitionId}`
- `POST /agent/chat`
- `POST /agent/actions/{messageId}/approve`
- `POST /agent/actions/{messageId}/reject`
- `GET /agent/sessions`
- `GET /agent/sessions/{sessionId}`
- `DELETE /agent/sessions/{sessionId}`
- `GET /agent/tools`

Settings usage:
- `AgentsTab.tsx`

Modular backend routes present:
- `GET /v1/api/agent/definitions?active_only=...`
- `GET /v1/api/agent/definitions/{definitionId}`
- `POST /v1/api/agent/definitions`
- `PATCH /v1/api/agent/definitions/{definitionId}`
- `DELETE /v1/api/agent/definitions/{definitionId}`
- `POST /v1/api/agent/chat`
- `POST /v1/api/agent/actions/{messageId}/approve`
- `POST /v1/api/agent/actions/{messageId}/reject`
- `GET /v1/api/agent/sessions`
- `GET /v1/api/agent/sessions/{sessionId}`
- `DELETE /v1/api/agent/sessions/{sessionId}`
- `GET /v1/api/agent/tools`

Assessment:
- `exact`
- recent agent-runtime PRs added the full settings-facing runtime admin surface on the generic modular router

### Agent Traces

Required capability:
- list trace runs
- inspect a specific run

Frontend endpoints:
- `GET /agent-traces/runs`
- `GET /agent-traces/runs/{runId}`

Settings usage:
- `AgentTracesTab.tsx`

Modular backend routes present:
- `GET /v1/api/agent-traces/runs`
- `GET /v1/api/agent-traces/runs/{runId}`

Assessment:
- `exact`
- recent agent-runtime PRs added the same trace list/detail routes the settings UI expects

### Playbooks

Required capability:
- list/get/create/update playbook definitions
- start, list, inspect, pause, resume, cancel runs
- list/get/complete/execute step runs

Frontend endpoints:
- `GET /playbooks`
- `GET /playbooks/{playbookId}`
- `POST /playbooks`
- `PATCH /playbooks/{playbookId}`
- `POST /playbooks/runs`
- `GET /playbooks/runs`
- `GET /playbooks/runs/{runId}`
- `POST /playbooks/runs/{runId}/pause`
- `POST /playbooks/runs/{runId}/resume`
- `POST /playbooks/runs/{runId}/cancel`
- `GET /playbooks/runs/{runId}/steps`
- `GET /playbooks/steps/{stepRunId}`
- `POST /playbooks/steps/{stepRunId}/complete`
- `POST /playbooks/steps/{stepRunId}/execute`

Settings usage:
- `PlaybooksTab.tsx`
- `PlaybookBuilder/index.tsx`

Modular backend routes present:
- `GET /v1/api/playbooks/status`
- `GET /v1/api/playbooks_runtime/status`

Assessment:
- `missing`

## Frontend vs Modular Backend Mapping Matrix

| Domain | Frontend Endpoint Family | Exact Modular Match | Adjacent Modular Routes | Coverage |
| --- | --- | --- | --- | --- |
| State machines | `/state-machines*` | Yes | `/v1/api/state-machines*` | Exact |
| Funnels | `/config/funnels*` | No | `/v1/api/metadata_registry/funnel/resolve`, `/v1/api/projections/pipeline-funnels` | Partial-adjacent |
| Form schemas | `/config/forms*`, `/config/seed` | No | `/v1/api/forms/configs*`, `/v1/api/metadata_registry/form-configs*` | Partial-adjacent |
| Picklists | `/config/picklists*` | No | None | Missing |
| Integrations | `/integrations*` | No | `/v1/api/integrations*`, `/v1/api/integrations_calendar*` | Partial-adjacent |
| Users | `/users*` | No | `/v1/api/auth/*`, `/v1/api/identity_access/*` | Missing |
| Invitations | `/invitations*` | No | None | Missing |
| Organizations | `/organizations*` | No | `/v1/api/organizations/status`, `/v1/api/tenants/status` | Missing |
| Roles | `/roles*` | No | `/v1/api/auth/roles/grant`, `/v1/api/identity_access/roles/grant` | Missing |
| Document types | `/config/document-types*` | No | `/v1/api/documents*` | Missing |
| Jobs | `/jobs*` | No | `/v1/api/background_jobs/intake-jobs*`, `/v1/api/intake/jobs*`, `/v1/api/tasks*` | Partial-adjacent |
| LLM config | `/config/llm-keys*` | No | `/v1/api/llm/status` | Missing |
| Email config | `/config/email*` | No | `/v1/api/communications/email-config*`, `/v1/api/collaboration/email-config*` | Partial-adjacent |
| Transcription config | `/config/transcription*` | No | `/v1/api/transcription/status` | Missing |
| AI features | `/config/ai-features*` | No | None | Missing |
| Agent definitions | `/agent/*` | Yes | `/v1/api/agent/*` | Exact |
| Agent traces | `/agent-traces*` | Yes | `/v1/api/agent-traces/*` | Exact |
| Playbooks | `/playbooks*` | No | `/v1/api/playbooks/status`, `/v1/api/playbooks_runtime/status` | Missing |

## Roadmap Implications

If the product goal is to preserve current settings functionality, the backend roadmap needs to cover all of the following before the modular settings UI can be considered functionally complete:

1. Workflow admin APIs
   - funnel CRUD, versioning, validation, publish

2. Configuration registry APIs
   - form configs
   - picklists
   - document types
   - AI feature mappings

3. Platform admin APIs
   - users
   - invitations
   - organizations
   - RBAC roles and permission summaries

4. Provider configuration APIs
   - LLM credentials
   - email credentials and test send
   - transcription credentials and model discovery
   - calendar and other user integrations

5. Runtime admin and observability APIs
   - jobs
   - playbook definitions and execution runtime

## Rationalization Guardrail

The current matrix should be used as the baseline before API rationalization. If rationalization begins now without preserving these capability buckets, the likely regressions are:
- losing approval and lifecycle transitions that are modeled today as action endpoints
- losing version/publish semantics for funnels
- losing validation and test flows for provider configs
- losing run-control actions for playbooks and jobs
- losing admin-only tenant and RBAC operations

That means the next step should not be removing endpoints blindly. The next step should be defining canonical resource models that still preserve:
- CRUD where the UI manages durable resources
- action endpoints where the UI performs transitions, validation, publish, test, OAuth, or run-control operations
