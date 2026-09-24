# Frontend Implementation Progress

**Last Updated:** 22 January 2026
**Status:** Core ATS UI Complete, Multi-Tenancy Support, Entity Type-Driven Navigation, Document Type-Driven Upload, Document Agent Tool Configuration, Multi-Organization Membership (v0.12), Calendar Integration & Interview Scheduling (v0.13), **Requisition Entity & Job Prioritization (v0.14)** Complete

> **Note (14 January 2026):** Backend Phase 4 (Action Library) has been superseded by the Unified Agent Architecture. Post-processing actions are now handled by configuring agent instructions and tools in DocumentTypeConfig, eliminating the need for a dedicated Action Library UI.

---

## Overview
The frontend implements the **ATS Cockpit UI** for the state machine workflow runtime. Built with React, TypeScript, and Tailwind CSS, it follows the Newtuple Design Language defined in `styleguide.MD` with a focus on minimalistic, HR-friendly user experience.

---

## Technology stack
- **Framework:** React 19 + TypeScript
- **Build Tool:** Vite 5.4
- **Styling:** Tailwind CSS 3.x
- **Icons:** Lucide React (outline style)
- **Routing:** React Router DOM
- **Architecture:** Component-based with hooks for data fetching

---

## Completed components

### 1. Project Setup & Infrastructure
- **Build Configuration**: Vite setup, TypeScript strict mode, API proxy to backend.
- **Design System**: Newtuple color palette (Cobalt Blue #0047AB), system font stack, custom Tailwind theme extensions.
- **API Client**: Typed API methods for entities, transitions, bulk operations, events, and state machines.

### 2. Layout & Navigation
- **App Layout**: Fixed header, desktop sidebar, mobile bottom navigation.
- **Navigation**: Active route highlighting and responsive transitions.

### 3. Pipeline Board
- **Kanban View**: 7-column board (APPLIED → JOINED) with live data fetching.
- **Application Cards**: Candidate/Job info, SLA badges, risk indicators.
- **Drag-and-Drop**: @dnd-kit integration with visual feedback and forward-only move enforcement.
- **Bulk Actions**: Selection mode, multi-select cards, and fixed bottom action bar for bulk transitions.

### 4. Detail Views & Modals
- **Application Detail**: Slide-over panel with state banner, candidate/job info, and real activity timeline.
- **Job Detail**: Stats cards, pipeline summary, and integrated applicant list.
- **Modals**: Create/Edit Job, Create/Edit Candidate, Add Application.

### 5. Domain Pages
- **Jobs Page**: Searchable/filterable grid of open positions with integrated stats.
- **Candidates Page**: Sortable table with advanced date range and source filtering.
- **Settings Page**: Tabbed interface with Pipeline Funnel and State Machine views.

### 6. Skin Manifest System
- **SkinProvider**: Context-based skin configuration loaded from backend `/api/ui/skin`.
- **useSkin Hook**: Access skin config (nav items, colors, field mappings, static lists).
- **useStateMachine Hook**: Derived state machine data (stages, transitions, triggers).
- **Dynamic Navigation**: Sidebar/mobile nav driven by skin configuration.
- **Field Mapping**: Entity fields mapped to UI labels via skin manifest.

### 7. Edit Application & Pipeline Funnel
- **EditApplicationModal**: Form for editing application metadata (phone, source, notes).
- **PipelineFunnel**: Vertical timeline visualization of pipeline stages with SLA and transition counts.
- **StageDetailDrawer**: Right-side drawer showing stage configuration (SLA, guards, transitions).
- **FunnelSettingsTab**: Container component with responsive layout (inline desktop, drawer mobile).
- **funnelLabels Utility**: HR-friendly terminology mapping (Guards → "Move Requirements", etc.).

### 8. Transition Visibility (Option E - Hybrid)
Progressive disclosure of state transitions with guard-aware UI:
- **TransitionBadge**: Shows "→ N" badge on column headers for transition count.
- **TransitionTooltip**: Hover tooltip listing available next states with colors.
- **ColumnHeaderPanel**: Expandable panel with guard details and execute buttons.
- **GuardStatusList**: Reusable component showing passed/failed guards with descriptions.
- **Drag-and-Drop States**: Visual feedback - valid (green), blocked (amber), invalid (gray).
- **AvailableActionsSection**: Guard-aware actions in ApplicationDetail with requirement status.
- **useAvailableTransitions Hook**: Fetch and cache available transitions with guard evaluation.

### 9. Funnel Builder UI (Integrated with Backend)
Full funnel management interface with real API integration:
- **FunnelsTab**: Container managing list/builder view toggle with API fetching.
- **FunnelList**: Table view of funnels with status badges, version, job count.
- **FunnelBuilder**: Step-based editor with validation panel.
  - **BasicsStep**: Funnel name, machine name (auto-generated), description.
  - **StagesStep**: Vertical stage list with add/edit/reorder, color picker, initial/terminal flags.
  - **TransitionsStep**: Per-stage transition configuration with trigger naming.
  - **GuardsStep**: HR-friendly guard rule builder (FIELD_PRESENT, HITL_REQUIRED, etc.).
  - **SlaStep**: Per-stage SLA duration presets and custom input.
  - **ValidationPanel**: Inline error/warning display with step navigation.
- **API Integration**: Full CRUD via `/config/funnels` endpoints with funnelConverter utility.
- **Types**: Full TypeScript types for Funnel, Stage, Transition, Guard.

### 10. Dynamic Pipeline Board (Multi-Funnel Support)
Pipeline board that renders columns based on selected job's funnel:
- **useDynamicStateMachine Hook**: Dynamically loads state machine based on machine_name parameter.
  - Uses cached skin data when machine_name matches default (no extra fetch).
  - Fetches and derives stages/transitions for custom funnels.
- **Job Funnel Tracking**: PipelineBoard fetches jobs with their `pipeline_machine_name`.
- **Job-Based Filtering**: Job filter uses job IDs, tracks selected job's funnel.
- **Dynamic Columns**: Renders pipeline columns from selected job's funnel stages.
- **Multi-Funnel Detection**: Detects when applications span multiple funnels.
- **Warning Banner**: Shows amber banner when "All Jobs" selected with multiple funnels detected.
- **Protected Actions**: Disables drag-and-drop and bulk transitions in multi-funnel mode.
- **useFunnels Hook**: Reusable hook for fetching published funnels (used in job modals).

### 11. Dashboard Analytics
Full analytics dashboard with three visualization views:
- **DashboardPage**: Tab-based analytics page with Pipeline Funnel, SLA Heatmap, and Conversion Metrics tabs.
- **PipelineFunnel Component**: Recharts FunnelChart showing candidate counts and drop-off percentages per stage.
- **SLAHeatmap Component**: Grid of jobs vs stages with color-coded cells (OK/Warning/Critical) based on breach rates.
- **ConversionMetrics Component**: Key metric cards (time-to-hire, overall conversion, bottleneck stage) plus stage duration bar chart and per-stage conversion rate visualization.
- **useAnalytics Hook**: Fetches and transforms pipeline/heatmap data into chart-ready formats.
- **Projections API**: Extended API client with `/projections/pipeline` and `/projections/heatmap` endpoints.

---

## Future work

### Authentication & Authorization (Complete)
- [x] **Auth Context** (`core/auth/AuthContext.tsx`):
    - `AuthProvider` wrapping the app with user state management.
    - `useAuth()` hook exposing: user, organization, isLoading, isAuthenticated, login, loginWithGoogle, logout, hasRole.
    - User type: id, email, fullName, avatarUrl, role (admin/recruiter/hiring_manager/viewer), authType (local/google), organizationId.
    - Organization type: id, name, slug, logoUrl.
    - Auto-fetches organization when user has organizationId.
- [x] **Token Management** (`core/auth/api.ts`):
    - Access token stored in memory (React state) - short-lived (30 min).
    - Refresh token stored in localStorage.
    - Auto-refresh on 401 response with retry logic.
    - Clear tokens on logout.
- [x] **API Client Updates** (`core/services/api.ts`):
    - Add `Authorization: Bearer <token>` header to all requests.
    - Intercept 401 responses → attempt token refresh → retry request.
    - Redirect to `/login` on refresh failure.
- [x] **Login Page** (`pages/LoginPage.tsx`):
    - Email/password form for local authentication.
    - "Sign in with Google" button initiating OAuth flow.
    - Error display for invalid credentials.
    - Redirect to `/` on successful login.
- [x] **Google OAuth Callback** (`pages/GoogleCallbackPage.tsx`):
    - Handle redirect from Google with auth code.
    - Exchange code via `POST /auth/google/callback`.
    - Store tokens and redirect to `/`.
    - Error handling for OAuth failures.
- [ ] **Registration Page** (`/register`) (optional):
    - Local user registration form (if open registration enabled).
    - Email, password, full name fields.
    - Validation and error handling.
- [x] **Protected Routes** (`core/auth/ProtectedRoute.tsx`):
    - `ProtectedRoute` component checking authentication status.
    - Redirect unauthenticated users to `/login`.
    - Role-based route protection with `roles` prop.
    - Loading state while checking auth.
- [x] **AppLayout Updates** (`layouts/AppLayout.tsx`):
    - Replace hardcoded "HR" badge with user avatar/initials.
    - User dropdown menu: profile info, role badge, logout button.
    - Show user's full name in header.
- [ ] **Role-Based UI**:
    - Hide/disable UI elements based on user role.
    - Admin-only sections in Settings.
    - Recruiter vs Hiring Manager action visibility.
    - `hasRole()` helper for conditional rendering.

### Multi-Tenancy Support (Complete)
- [x] **Organization Types** (`core/auth/types.ts`):
    - `Organization` interface: id, name, slug, domain, settings, status, logoUrl, timestamps.
    - `OrganizationPublic` interface: id, name, slug, logoUrl (minimal for embedding).
    - `OrganizationStatus` type: active, suspended, archived.
- [x] **Auth Context Updates**:
    - Added `organization` state to AuthContext.
    - `useAuth()` hook now exposes `organization` alongside `user`.
    - Auto-fetches current organization when user is authenticated.
    - Clears organization on logout.
- [x] **Auth API Updates** (`core/auth/api.ts`):
    - `getCurrentOrganization()`: Fetches `/organizations/current` endpoint.
    - `transformOrganization()`: Converts snake_case API response to camelCase.
    - User response now includes `organizationId` field.

### Phase 2: Refinement & Generalization
- [x] **Edit Application Data**: Form to edit existing application details and metadata (phone, source, notes).
- [x] **Skin Manifest**: Multi-skin UI support via central configuration (nav, field mappings, static lists).
- [ ] **User Preferences**: Theme selection (Light/Dark), default filter presets, and notification settings.
- [ ] **Multi-select Filters**: Support for complex filter combinations (e.g., Job + Source + TimeRange) across all listings.
- [ ] **Dynamic Board**: Drive pipeline columns, labels, colors, and allowed transitions entirely from state machine definitions + UI metadata (removing hard-coded ATS logic).
- [x] **Transition Visibility (Option E - Hybrid)**: Progressive disclosure of state transitions on pipeline board (see Section 8).

### Phase 3: Advanced Orchestration & Analytics
- [x] **Pipeline Funnel Settings**: Stage-centric UI with vertical timeline, jargon mapping, and stage detail drawer.
- [x] **FUNNEL-MULTI-001 — Multiple funnels per Job + full Funnel Builder (Settings-first)** (Complete):
    - **Goal**: Allow multiple pipeline funnels (different `machine_name`s) to be created in the system and assigned per Job, without breaking the generalized entity engine.
    - **Naming convention (enforced)**:
        - Funnel Builder must enforce ATS funnel machine naming regex:
          - `^ats_application_[a-z0-9]+(?:_[a-z0-9]+)*$` (lowercase slug, underscores, max 128 chars).
        - Funnel Builder auto-generates machine name from Funnel Name (slugify) with inline validation + suggestions.
        - Advanced field: “Machine name” editable only before first publish; after publish it is immutable (new funnel required to change).
    - **Settings IA**:
        - Add Settings tab: **Funnels** (separate from raw “State Machines” view).
        - **Funnels list** (minimal): Funnel Name, machine name (secondary), status, latest version, “Used by X jobs”, last updated.
        - Progressive disclosure: click row → Funnel Builder; kebab actions: Duplicate, Archive, View JSON (advanced).
    - **Funnel Builder UX (progressive disclosure)**:
        - **Basics**: Funnel Name, Description, Machine Name (validated), Tags.
        - **Stages**: Vertical stage list with add/reorder; initial + terminal indicators; confirm-before-delete.
        - **Next Steps** (Transitions): Select a stage → configure allowed next states; optional “Show map” overlay toggle for arrows.
        - **Move Requirements** (Guards): Human-friendly rule builder mapped to guard types (FIELD_PRESENT, POLICY_CHECK, RELATION_EXISTS, HITL_REQUIRED).
        - **SLA & Alerts**: Per-stage SLA durations; optional reminders/escalations (signals) in later iteration.
        - **Validation**: Inline errors and warnings (missing initial, unreachable states, duplicate triggers, terminal with outgoing).
    - **Publishing + versioning model**:
        - Draft → Published workflow.
        - Editing a Published funnel creates a new version (v+1) and keeps older versions immutable.
        - “Publish” button shows summary of changes + impact notice.
    - **Job-level funnel assignment**:
        - Jobs UI: add “Funnel” selector (Published funnels) in Job settings/edit.
        - Persist selection on Job entity `data` (generalized metadata; no new job schema required):
          - `pipeline_machine_name`, `pipeline_machine_version`
        - Default behavior: funnel changes apply to **new applications only** (explicit copy text).
    - **Add Application behavior**:
        - When selecting a job, show “This job uses funnel: <name>”.
        - Application creation uses job’s funnel machine key; fallback to default only if job has none.
    - **Pipeline Board behavior (minimalist, safe)** (Complete):
        - When "All Jobs" and multiple funnels detected: show banner "Multiple funnels detected. Select a job to view its pipeline."
        - Disable drag/drop + bulk transitions until job filter selected (prevents wrong transition assumptions).
        - When job selected: render columns + Option E transition hints from that funnel's state machine.
        - Dynamic state machine loading via `useDynamicStateMachine` hook.
    - **Non-goals (v1)**:
        - No automatic migration of existing applications across funnels.
        - No multi-funnel combined board view (requires complex grouping; avoided by design).
- [ ] **Funnel Builder - Field Autocomplete**: In the Guards/Move Requirements step, show available field names from the entity schema (e.g., `candidate_phone`, `candidate_email`, `notes`) as autocomplete suggestions when configuring FIELD_PRESENT guards. Prevents field name mismatches where users enter `phone` but data is stored as `candidate_phone`.
- [ ] **Stage Checklist Component**: Vertical progress tracker in application detail showing live playbook execution.
- [x] **Requirement Tooltips**: Visual feedback for failed guards on disabled transition buttons (Complete):
    - `RequirementTooltip` component showing failed guards on hover.
    - Integrated in `AvailableActionsSection` (disabled action buttons).
    - Integrated in `ColumnHeaderPanel` (blocked transition messages).
- [x] **Dashboard**: Specialized analytics views (Complete):
    - **Pipeline Funnel Analytics**: Drop-off rates between stages using Recharts FunnelChart.
    - **SLA Heatmap**: Grid visualization of jobs vs stages with breach severity color-coding.
    - **Conversion Metrics**: Time-to-hire, overall conversion rate, stage duration bar chart, and per-stage conversion rates.
    - Tab-based navigation between views with refresh capability.
    - Uses `/projections/pipeline` and `/projections/heatmap` backend APIs.
- [ ] **Real-time Notifications**: WebSocket-driven alerts for SLA breaches, interventions, and playbook assignments.
- [ ] **Global Search**: Cross-entity search (Candidates, Jobs, Applications) with advanced filtering.

### Phase 4: Pipeline Views & Data Import
- [x] **Pipeline List View** (Complete):
    - **View Toggle**: Button group to switch between Kanban and List views on Pipeline page.
    - **List Table**: Sortable columns (Candidate, Job, State, SLA Due, Applied Date, Source).
    - **State Badges**: Color-coded state badges matching Kanban column colors via `StateBadge` component.
    - **Inline Actions**: Quick action buttons (view details, move to next state) per row with dropdown for additional transitions.
    - **Bulk Selection**: Checkbox column for selecting multiple applications.
    - **Bulk Actions Bar**: Same actions as Kanban bulk mode (move selected, etc.).
    - **Pagination**: Client-side pagination with page size of 25, page number navigation.
    - **Preserve Filters**: Same job/state filters work across both views.
    - Component: `frontend/src/domains/ats/components/pipeline/PipelineListView.tsx`
- [ ] **Bulk CSV/Spreadsheet Upload UI**:
    - **Upload Modal**: Drag-and-drop zone for CSV/Excel files.
    - **Entity Type Selector**: Choose between Candidates or Applications import.
    - **Column Mapping Preview**: Show LLM-suggested mappings with ability to override.
    - **Data Preview Table**: Display first N rows with mapped columns.
    - **Validation Errors**: Inline error indicators for invalid rows (bad email, missing required fields).
    - **Duplicate Warnings**: Highlight rows that match existing records.
    - **Confirm & Import**: Button to execute import with progress indicator.
    - **Import Summary**: Success/failure counts after completion.
- [x] **Bulk PDF Resume Upload UI** (Complete):
    - **Upload Zone**: Multi-file drag-and-drop for PDF resumes (max 20 files, 10MB each).
    - **Processing Status**: Progress bar showing extraction status with completed/failed/remaining counts.
    - **Split-Screen Preview**:
        - Left sidebar: File list with extraction status icons and duplicate indicators.
        - Center panel: PDF viewer (iframe) showing original resume.
        - Right panel: Editable form with extracted data (name, email, phone, location, LinkedIn, skills, notes).
    - **Navigation**: Previous/Next buttons to cycle through uploaded resumes with index counter.
    - **Edit & Confirm**: User can correct extracted data before confirming, confidence score indicator.
    - **Batch Actions**: "Confirm All" to create all candidates at once.
    - **Duplicate Detection**: Full duplicate handling dialog with options to Update existing, Create new, or Skip.
    - **Systemic Error Handling**: AI configuration error banner with manual entry fallback.
    - Component: `frontend/src/domains/ats/components/ResumeUploadModal.tsx`

### Phase 5: Dynamic Form System (Complete)
- [x] **Dynamic Form Schema System**:
    - **FormSchema API**: Fetch entity-specific form schemas from `/form-config/schemas/{entity_type}`.
    - **Picklist API**: Fetch picklist options from `/form-config/picklists` for select/multi-select fields.
    - **DynamicFormFields Component**: Generic renderer supporting all field types (text, email, phone, url, number, date, textarea, select, multi_select, boolean).
    - Components: `frontend/src/domains/ats/components/DynamicFormFields.tsx`, `frontend/src/core/types/index.ts`
- [x] **Job Form (Complete Fields)**:
    - All fields: title, department (picklist), location (picklist), hiring_manager, status, pipeline_machine_name.
    - **Picklist Integration**: Department and location use database picklists with fallback to skin static lists.
    - **Funnel Assignment**: Dropdown to select pipeline funnel from published funnels via `useFunnels` hook.
    - Components: `CreateJobModal.tsx`, `EditJobModal.tsx`
- [x] **Candidate Form (Dynamic Schema-Driven)**:
    - Fetches FormSchema from API at modal open.
    - Dynamically renders all fields defined in schema (full_name, email, phone, location, linkedin_url, skills, source, notes, etc.).
    - **Validation**: Required field validation, email format validation.
    - **Fallback**: Static form if no schema available.
    - Components: `CreateCandidateModal.tsx`, `EditCandidateModal.tsx`
- [x] **Application Form (Dynamic Schema-Driven)**:
    - Fetches FormSchema from API for application entity type.
    - Dynamically renders custom fields based on schema.
    - All fields editable with proper field type rendering.
    - Components: `AddApplicationModal.tsx`, `EditApplicationModal.tsx`

### Phase 6: Multi-Organization Membership (v0.12) ✅ COMPLETE (20 January 2026)
- [x] **Self-Service Organization Registration**:
    - **LoginPage Enhancement**: New "Create Organization" tab alongside existing login/register.
    - **Registration Form**: Email, password, full name, organization name fields.
    - **Slug Generation**: Auto-generate URL-friendly slug from organization name.
    - **Pending State Flow**: After registration, redirect to PendingOrgApprovalPage.
    - Component: `frontend/src/pages/LoginPage.tsx`
- [x] **PendingOrgApprovalPage**:
    - Shows "Waiting for Approval" status with organization details.
    - Displays helpful information about the approval process.
    - Logout button to return to login page.
    - Component: `frontend/src/pages/PendingOrgApprovalPage.tsx`
- [x] **OrganizationsTab (Super-Admin)**:
    - **Settings Integration**: New "Organizations" tab in Settings for super-admins.
    - **Pending List**: Table showing pending organization requests with requester info.
    - **Approve/Reject Actions**: Buttons to approve or reject pending organizations.
    - **Active Organizations**: Expandable section showing all active organizations.
    - Component: `frontend/src/domains/ats/components/settings/OrganizationsTab.tsx`
- [x] **OrgSelector (Super-Admin Context Switching)**:
    - **Header Dropdown**: Allows super-admins to switch organization context.
    - **IntegrationsTab Integration**: LLM keys, email config view org-specific settings.
    - **Context Provider**: `OrgSelectorContext` for global org selection state.
    - Components: `frontend/src/core/components/OrgSelector.tsx`, `frontend/src/core/contexts/OrgSelectorContext.tsx`
- [x] **UserOrgSwitcher (Multi-Org Users)**:
    - **Header Dropdown**: Allows users in multiple orgs to switch their active organization.
    - **Organization List**: Shows all organizations user belongs to with role.
    - **Current Indicator**: Checkmark on currently active organization.
    - **Switch Action**: Calls API to switch org, then reloads page for fresh data.
    - Component: `frontend/src/core/components/UserOrgSwitcher.tsx`
- [x] **Auth Context Enhancements**:
    - **organizations State**: List of user's organization memberships.
    - **switchOrganization Function**: API call to switch active organization.
    - **fetchOrganizations**: Fetches user's org memberships on login.
    - New types: `UserOrganizationMembership`, `UserOrganizationsResponse`.
- [x] **API Client Updates**:
    - `authApi.getMyOrganizations()` - Fetch user's organization memberships.
    - `authApi.switchOrganization(orgId)` - Switch active organization.
    - Config APIs support `org_id` parameter for super-admin cross-org access.
    - Fixed header merging bug in `authRequest` causing 422 errors.

### Phase 7: Calendar Integration & Interview Scheduling (v0.13) ✅ COMPLETE (21 January 2026)

**Overview**: Full calendar integration enabling recruiters to schedule interviews directly from the application detail view. Uses Google Calendar if connected, with ICS email fallback for universal compatibility.

#### Backend (Platform Primitives)
- [x] **Google Calendar OAuth 2.0**:
    - `GET /integrations/google-calendar/auth-url` - Initiates OAuth popup flow
    - `GET /integrations/google-calendar/callback` - Handles OAuth code exchange
    - `DELETE /integrations/google-calendar/disconnect` - Revokes access and removes credentials
    - `GET /integrations/google-calendar/status` - Returns connection status for current user
    - Credentials encrypted and stored per-user in `UserIntegration` table
    - Service: `backend/app/services/calendar/google_calendar.py`
- [x] **CalendarService (Dual Provider)**:
    - Attempts Google Calendar API first if user has valid credentials
    - Falls back to ICS email attachment if Google not connected or fails
    - Creates calendar events with attendees, location, description
    - Service: `backend/app/services/calendar/service.py`
- [x] **`send_calendar_invite` MCP Tool**:
    - Registered in document agent tool manifest
    - Can be used by playbooks and agents to schedule interviews programmatically
    - Accepts: title, date, start_time, duration, attendees, description, location
    - Service: `backend/app/services/calendar/tools.py`

#### Backend (ATS-Specific Convenience Endpoint)
- [x] **Scheduling API**:
    - `POST /scheduling/applications/{application_id}/interviews`
    - Auto-generates title: "Interview: {candidate} - {job}"
    - Reads candidate data from application.data (denormalized)
    - Creates audit event in entity timeline
    - Schema: `backend/app/schemas/scheduling.py`
    - Route: `backend/app/api/routes/scheduling.py`

#### Frontend
- [x] **GoogleCalendarConnectButton Component**:
    - Shows connection status (Connected/Not Connected)
    - "Connect" button opens OAuth popup
    - "Disconnect" button with confirmation
    - Component: `frontend/src/domains/ats/components/settings/GoogleCalendarConnectButton.tsx`
- [x] **IntegrationsTab Enhancement**:
    - Google Calendar section showing connection status per user
    - Inline connect/disconnect controls
    - Component: `frontend/src/domains/ats/components/settings/IntegrationsTab.tsx`
- [x] **ScheduleInterviewModal Component**:
    - Date picker (native HTML input, min=today)
    - Time picker (24-hour format)
    - Duration selector (30, 45, 60, 90, 120 minutes)
    - Timezone selector (auto-detects browser timezone)
    - Title field (pre-filled with candidate/job)
    - Location/meeting link field
    - Description textarea
    - Additional attendees (multi-line email input)
    - "Send invites" checkbox
    - Success state with Google Calendar link (if applicable)
    - Component: `frontend/src/domains/ats/components/ScheduleInterviewModal.tsx`
- [x] **ApplicationDetail Integration**:
    - Prominent "Schedule" button (cobalt blue) next to Edit button
    - Only shown for non-terminal states
    - On success: refreshes activity timeline
    - Component: `frontend/src/domains/ats/components/ApplicationDetail.tsx`
- [x] **TypeScript Types**:
    - `ScheduleInterviewRequest` and `ScheduleInterviewResponse` interfaces
    - `scheduling.scheduleInterview()` API method
    - Types: `frontend/src/core/types/index.ts`
    - API: `frontend/src/core/services/api.ts`

#### Files Created/Modified
| File | Action | Purpose |
|------|--------|---------|
| `backend/app/schemas/scheduling.py` | Created | Pydantic request/response models |
| `backend/app/api/routes/scheduling.py` | Created | Interview scheduling endpoint |
| `backend/app/api/routes/__init__.py` | Modified | Export scheduling_router |
| `backend/app/api/__init__.py` | Modified | Export scheduling_router |
| `backend/app/main.py` | Modified | Include scheduling router |
| `frontend/src/core/types/index.ts` | Modified | Add scheduling TypeScript types |
| `frontend/src/core/services/api.ts` | Modified | Add scheduling API method |
| `frontend/src/domains/ats/components/ScheduleInterviewModal.tsx` | Created | Scheduling modal UI |
| `frontend/src/domains/ats/components/ApplicationDetail.tsx` | Modified | Add Schedule button and modal |

### Supporting Components (Phase 5 Dependencies)
- [ ] **File Upload Component**:
    - Drag-and-drop zone with click-to-browse fallback.
    - File type validation (PDF, DOCX, images).
    - Upload progress indicator.
    - Preview thumbnail for images, icon for documents.
    - Delete/replace capability.
    - Integration with backend File Storage Service.
- [ ] **Rich Text Editor**:
    - Lightweight editor (Tiptap or similar).
    - Basic formatting: bold, italic, bullet lists, numbered lists, links.
    - Paste from Word/Google Docs with cleanup.
    - Character/word count (optional).
- [ ] **Tags Input Component**:
    - Multi-value input with autocomplete suggestions.
    - Create new tags inline.
    - Fetch existing tags from backend for suggestions.
    - Keyboard navigation (Enter to add, Backspace to remove).

### Phase 8: Requisition Entity & Job Prioritization (v0.14) ✅ COMPLETE

**Overview**: Add a Requisitions page for managing job requisitions with drag-and-drop priority reordering. Priority cascades from Requisition to linked Jobs, and Jobs page shows inherited priority.

#### New Types (`domains/ats/types/requisition.ts`)
```typescript
export type RequisitionStatus = 'OPEN' | 'FILLED' | 'CANCELLED';

export interface Requisition {
  entity_id: string;
  entity_type: 'Requisition';
  data: {
    title: string;
    department?: string;
    location?: string;
    headcount: number;
    priority_score: number;  // 0-100, higher = more urgent
    target_close_date?: string;
    status: RequisitionStatus;
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

#### API Methods (`domains/ats/services/api.ts`)
- [x] `requisitions.list(filters?)` - List all requisitions
- [x] `requisitions.get(id)` - Get single requisition with linked jobs
- [x] `requisitions.create(data)` - Create new requisition
- [x] `requisitions.update(id, data)` - Update requisition
- [x] `requisitions.updatePriority(id, score)` - Update priority and cascade to jobs
- [x] `requisitions.reorder(ids)` - Bulk reorder by position (assigns scores automatically)

#### RequisitionsPage (`domains/ats/pages/RequisitionsPage.tsx`) ✅ COMPLETE
- [x] **Sortable List View**:
    - Drag-and-drop reordering with @dnd-kit (already used in PipelineBoard)
    - Drag handle on left side of each row
    - On drop: calls `requisitions.reorder()` with new order
    - Optimistic update for smooth UX
- [x] **List Columns**:
    - Drag handle (grip icon)
    - Title (primary)
    - Department
    - Headcount (e.g., "3 positions")
    - Status badge (OPEN=green, FILLED=blue, CANCELLED=gray)
    - Target close date (red if overdue)
    - Linked jobs count (clickable to expand)
    - Actions (Edit, View Jobs, Archive)
- [x] **Filters**:
    - Status filter (OPEN, FILLED, CANCELLED, All)
    - Department dropdown
    - Search by title
- [x] **Create/Edit Modal** (`RequisitionModal.tsx`):
    - Title (required)
    - Department (picklist)
    - Location (picklist)
    - Headcount (number input, min 1)
    - Target close date (date picker)
    - Hiring manager (text or user picker)
    - Description (textarea)
    - Notes (textarea)
    - Link existing jobs to requisition

#### RequisitionDetail Slide-Over
- [x] **Header**: Title, status badge, priority indicator
- [x] **Info Section**: Department, location, headcount, target date, hiring manager
- [x] **Linked Jobs Section**:
    - List of jobs created from this requisition
    - "Create Job" button to spawn new job linked to requisition
    - Each job shows: title, status, application count
- [ ] **Activity Timeline**: Events related to this requisition (future enhancement)

#### JobsPage Updates (`domains/ats/pages/JobsPage.tsx`)
- [x] **Priority Column**: Add sortable priority_score column
- [x] **Requisition Link**: Show parent requisition (if linked)
- [x] **Priority Badge**: Visual indicator (HIGH/MEDIUM/LOW based on score thresholds)
- [x] **Default Sort**: Sort by priority_score descending

#### Navigation Updates
- [x] **Add Requisitions to sidebar** (`layouts/AppLayout.tsx`):
    - Icon: `clipboard-list` (Lucide)
    - Label: "Requisition Requests"
    - Position: After Jobs
- [x] **Add route** (`App.tsx`):
    - Path: `/requisitions`
    - Component: `RequisitionsPage`

#### Files to Create
| File | Purpose |
|------|---------|
| `domains/ats/types/requisition.ts` | Requisition TypeScript types |
| `domains/ats/pages/RequisitionsPage.tsx` | Main requisitions page with drag-drop |
| `domains/ats/components/RequisitionList.tsx` | Sortable list component |
| `domains/ats/components/RequisitionRow.tsx` | Draggable row component |
| `domains/ats/components/RequisitionModal.tsx` | Create/Edit modal |
| `domains/ats/components/RequisitionDetail.tsx` | Detail slide-over |

#### Files to Modify
| File | Change |
|------|--------|
| `domains/ats/services/api.ts` | Add requisition API methods |
| `domains/ats/pages/JobsPage.tsx` | Add priority column and requisition link |
| `layouts/AppLayout.tsx` | Add Requisitions nav item |
| `App.tsx` | Add /requisitions route |

---

## Platform Refactoring: Configuration-Driven UI (Airtable Model)

This section outlines frontend changes to support the backend's configuration-driven architecture. The goal is to remove hardcoded ATS assumptions and render UI entirely from configuration loaded from the backend.

### Current State Analysis

**Hardcoded ATS References in Frontend**:
- Entity type strings (`"ATS.Application"`, `"ATS.Candidate"`, `"ATS.Job"`) in API calls
- Component names and file structure assume ATS domain
- Pipeline board columns hardcoded to application states
- Form schemas partially dynamic but with ATS-specific defaults

**What's Already Dynamic**:
- `useSkin` hook loads navigation and field mappings from backend ✓
- `DynamicFormFields` renders forms from schema ✓
- `useDynamicStateMachine` loads state machine for selected funnel ✓
- Picklists loaded from backend ✓

---

### Phase 1: Entity Type-Driven UI (Aligns with Backend Phase 1) ✅ COMPLETE

**Goal**: Load entity types from API and use them to drive UI components

**Status**: Complete (11 January 2026)
- Types: `EntityType`, `EntityTypeSummary`, `EntityTypeFeatures` in `core/types/index.ts` ✅
- API: `entityTypes.list()`, `entityTypes.getSummaries()`, `entityTypes.get()`, `entityTypes.getFeatures()` ✅
- Hook: `useEntityTypes` in `core/hooks/useEntityTypes.ts` ✅
  - `entityTypes`, `summaries`, `loading`, `error`
  - `getEntityType(name)`, `getSummary(name)`
  - `hasFeature(typeName, feature)`
  - `getDisplayName()`, `getIcon()`, `getColor()`
  - `navEntityTypes` for navigation items
- Icon Utility: `core/utils/iconMap.ts` - Maps string icon names to Lucide components ✅
- Navigation: `AppLayout.tsx` now drives sidebar/mobile nav from entity types ✅
  - Fixed items: Dashboard, Pipeline, Settings
  - Entity items: Jobs, Candidates (from `navEntityTypes`)
  - Fallback to skin navigation during loading

**Future enhancements (not required for Phase 1)**:
- Create generic `EntityListPage` component
- Create generic `EntityDetailPanel` component
- Refactor ATS pages to use generic components

**Hook Interface: `useEntityTypes`** (`core/hooks/useEntityTypes.ts`):
```typescript
interface EntityType {
  name: string;
  displayName: string;
  description: string;
  icon: string;
  color: string;
  features: {
    hasLifecycle: boolean;
    hasProjection: boolean;
    hasForm: boolean;
  };
}

function useEntityTypes(): {
  entityTypes: EntityType[];
  getEntityType: (name: string) => EntityType | undefined;
  isLoading: boolean;
}
```

**Dynamic Navigation**:
- Replace hardcoded nav items (Pipeline, Jobs, Candidates) with entity type-driven navigation
- Show nav item only if entity type has `hasForm: true` or `hasLifecycle: true`
- Use entity type `icon` and `displayName` for nav labels

**Entity List Pages**:
- Generic `EntityListPage` component that renders based on entity type config
- Columns derived from entity type schema fields
- Create/Edit modals load form schema from entity type

**Files to Create**:
| File | Purpose |
|------|---------|
| `core/hooks/useEntityTypes.ts` | NEW - Fetch and cache entity types |
| `core/components/EntityListPage.tsx` | NEW - Generic entity list component |
| `core/components/EntityDetailPanel.tsx` | NEW - Generic entity detail slide-over |

**Files to Modify**:
| File | Change |
|------|--------|
| `core/services/api.ts` | Add `getEntityTypes()` API method |
| `layouts/AppLayout.tsx` | Drive sidebar nav from entity types |
| `domains/ats/pages/*.tsx` | Refactor to use generic EntityListPage |

---

### Phase 2: Extraction-Driven Upload UI (Aligns with Backend Phase 2) ✅ COMPLETE

**Goal**: Load extraction configs from API to drive file upload modals

**Status**: Complete (11 January 2026)
- Implemented using `DocumentTypeConfig` API (aligns with backend DocumentTypeConfig model)
- Types: `core/types/index.ts` - DocumentType, DocumentTypeListResponse, etc. ✅
- API: `core/services/api.ts` - `documentTypes.list()`, `.get()`, `.create()`, `.update()`, `.delete()` ✅
- Hook: `core/hooks/useDocumentTypes.ts` - `useDocumentTypes()` with validation helpers ✅
- ResumeUploadModal refactored to load config from API ✅
  - Allowed extensions loaded from `DocumentTypeConfig.allowed_extensions`
  - Max file size loaded from `DocumentTypeConfig.max_size_mb`
  - File validation using `isFileValid()` helper from hook
  - UI dynamically shows configured values

**Hook: `useDocumentTypes`** (`core/hooks/useDocumentTypes.ts`):
```typescript
interface UseDocumentTypesResult {
  documentTypes: DocumentType[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  getDocumentType: (typeId: string) => DocumentType | undefined;
  getAllowedExtensions: (typeId: string) => string[];
  getMaxSizeBytes: (typeId: string) => number;
  isFileValid: (typeId: string, file: File) => { valid: boolean; error?: string };
  extractableTypes: DocumentType[];
}
```

**Files Created**:
| File | Purpose |
|------|---------|
| `core/hooks/useDocumentTypes.ts` | NEW - Fetch document type configs with validation |
| `core/types/index.ts` | UPDATED - Added DocumentType interfaces |

**Files Modified**:
| File | Change |
|------|--------|
| `core/services/api.ts` | Added `documentTypes` API methods |
| `core/hooks/index.ts` | Export `useDocumentTypes` |
| `domains/ats/components/ResumeUploadModal.tsx` | Uses `useDocumentTypes` for validation |

**Future enhancements (not blocking)**:
- Create a generic `GenericUploadModal` component for other document types
- Add upload button visibility based on extraction config targeting

---

### Document Agent Tool Configuration (13 January 2026) ✅ COMPLETE

**Overview**: Enhanced DocumentTypesTab in Settings to support agent-based document processing with configurable MCP tools.

**Features Implemented**:
- **Agent Processing Toggle**: Enable/disable agent processing per document type
- **Agent Instructions**: Textarea for custom agent prompt/instructions
- **Tool Presets**: Quick configuration buttons:
  - `Minimal`: Read-only tools (get_entity, list_entities, get_entity_state)
  - `Standard`: Minimal + entity updates
  - `Full`: All available tools
- **Tool Selection UI**:
  - Tools grouped by category (Document, Entity, Workflow, Communication, Integration)
  - Checkboxes for individual tool selection
  - Risk level badges with color coding:
    - `safe` (green): Read-only operations
    - `moderate` (yellow): Entity modifications
    - `caution` (red): Workflow changes, external communications
- **Agent Badge**: Visual indicator on document type cards when agent is enabled

**New Types** (`core/types/index.ts`):
```typescript
export type DocumentToolCategory = 'document' | 'entity' | 'workflow' | 'communication' | 'integration';

export interface DocumentAgentTool {
  name: string;
  category: DocumentToolCategory;
  description: string;
  risk_level: 'safe' | 'moderate' | 'caution';
  requires_confirmation: boolean;
}

export interface DocumentToolPreset {
  name: string;
  display_name: string;
  description: string;
  tools: string[];
}
```

**API Integration** (`core/services/api.ts`):
- `documentTypes.getTools()`: Fetches tool manifest with definitions and presets

**Files Modified**:
| File | Change |
|------|--------|
| `core/types/index.ts` | Added DocumentAgentTool, DocumentToolCategory, DocumentToolPreset types |
| `core/services/api.ts` | Added `getTools()` method to documentTypes API |
| `domains/ats/components/settings/DocumentTypesTab.tsx` | Added agent configuration UI section |

---

### Phase 3: View-Driven Dashboards (Aligns with Backend Phase 3)

**Goal**: Load view definitions from API to render projections/dashboards

**New Hook: `useViewDefinitions`** (`core/hooks/useViewDefinitions.ts`):
```typescript
interface ViewDefinition {
  name: string;
  displayName: string;
  sourceEntityType: string;
  groupBy: string;
  availableFilters: string[];
  slaConfig?: {
    warningHours: number;
    criticalHours: number;
  };
  aggregations?: Array<{
    name: string;
    type: 'count' | 'sum' | 'avg';
  }>;
}

function useViewDefinitions(): {
  views: ViewDefinition[];
  getView: (name: string) => ViewDefinition | undefined;
}
```

**Dynamic Pipeline Board**:
- Load view definition for "application_pipeline" (or whatever is configured)
- Columns derived from state machine + view's `groupBy` field
- Filters available based on view's `availableFilters`
- SLA badges configured by view's `slaConfig`

**Dynamic Dashboard**:
- Dashboard page loads available views with aggregations
- Render heatmap/funnel charts based on view's `aggregations` config
- Labels and groupings from view definition

**Files to Create**:
| File | Purpose |
|------|---------|
| `core/hooks/useViewDefinitions.ts` | NEW - Fetch view definitions |
| `core/components/DynamicPipelineBoard.tsx` | NEW - View-driven Kanban board |
| `core/components/DynamicDashboard.tsx` | NEW - View-driven analytics |

---

### Phase 4: Template Marketplace UI (Aligns with Backend Phase 5)

**Goal**: Allow admins to browse and install domain templates

**Template Browser** (Settings > Templates):
- List available templates from `GET /templates`
- Template cards showing: name, description, version, entity types included
- "Install" button to apply template to organization

**Template Preview**:
- Expand template to see what it contains:
  - Entity types (with icons/colors)
  - State machines (with stage counts)
  - Extraction configs (file types supported)
  - Views/projections included

**Post-Install Flow**:
- After install, prompt user to:
  - Configure API keys (if extraction configs need LLM)
  - Customize picklists (departments, locations)
  - Review form schemas

**Files to Create**:
| File | Purpose |
|------|---------|
| `domains/settings/components/TemplatesTab.tsx` | NEW - Template marketplace UI |
| `domains/settings/components/TemplateCard.tsx` | NEW - Template preview card |
| `domains/settings/components/TemplateInstallModal.tsx` | NEW - Install confirmation |

---

### Phase 5: Multi-Domain Navigation

**Goal**: Support multiple domains (ATS, PMO, CRM) in the same organization

**Domain Switcher**:
- Header dropdown to switch between installed domains
- Each domain has its own navigation items
- Persist selected domain in localStorage

**Domain Context**:
- `useDomain` hook provides current domain context
- Entity types filtered by domain prefix (e.g., `ATS.Candidate`, `PMO.Project`)
- Views filtered by domain

**Breadcrumb Updates**:
- Show domain name in breadcrumb: "ATS > Candidates > John Doe"

**Files to Create**:
| File | Purpose |
|------|---------|
| `core/contexts/DomainContext.tsx` | NEW - Domain context provider |
| `core/components/DomainSwitcher.tsx` | NEW - Domain selection dropdown |

---

### Implementation Order

| Phase | Effort | Backend Dependency | Status |
|-------|--------|---------------------|--------|
| **Phase 1**: Entity Type-Driven UI | Large | Backend Phase 1 | ✅ Complete |
| **Phase 2**: Extraction-Driven Upload UI | Medium | Backend Phase 2 | ✅ Complete |
| **Phase 3**: View-Driven Dashboards | Large | Backend Phase 3 | ❌ Not Started |
| **Phase 4**: Template Marketplace | Small | Backend Phase 5 | ❌ Not Started |
| **Phase 5**: Multi-Domain Navigation | Medium | All backend phases | ❌ Not Started |

---

### Success Criteria

After all phases:
1. Zero hardcoded entity type strings in frontend code
2. New entity types appear in navigation automatically
3. Upload modals configure themselves from extraction configs
4. Dashboard views render from backend configuration
5. Admin can install new domain templates from UI

---

## Known Issues / Bugs

**Last Updated:** 20 January 2026

### Notification Navigation Bug 🐛
**Priority:** High
**Status:** ✅ FIXED (20 January 2026)

Clicking on notifications does not navigate to the correct context:

1. **New User Registration Notification**
   - Expected: Should navigate to `http://localhost:5173/settings?tab=users`
   - Actual: Navigation doesn't work or goes to wrong location

2. **Application Link in Notifications**
   - Expected: `http://localhost:5173/pipeline?app={application_id}` should open the application detail
   - Actual: Link does not work - the `app` query parameter is not being read by PipelineBoard
   - Example: `http://localhost:5173/pipeline?app=851c3950-f6ad-4bf3-9e2c-7b23a3081ad0`

**Root Cause Analysis Needed:**
- Check `NotificationItem.tsx` - how are notification links generated?
- Check `PipelineBoard.tsx` - does it read `app` query param and auto-open detail panel?
- Check `SettingsPage.tsx` - does it read `tab` query param on mount?

**Fix Applied:**
- ✅ PipelineBoard now reads `app` query param on mount and auto-selects/opens that application
- ✅ SettingsPage now reads `tab` query param on mount and switches to that tab
- ✅ Tab changes in Settings now update the URL for bookmarkability
- NotificationItem link generation (backend) was already correct

---

## UI Improvement Recommendations

**Last Updated:** 11 January 2026

This section documents UI/UX improvement recommendations identified through code review and user experience analysis.

---

### 2. Pipeline Board Improvements

#### Visual Feedback & Animations
- [ ] **Smooth Card Animations**: Add smooth transitions when cards move between columns during drag-and-drop operations
- [ ] **Progress Indicators**: Show progress indicator during drag operations (e.g., loading spinner on card being moved)
- [ ] **Column Highlighting**: Add subtle column highlighting on hover (not just during drag) to improve discoverability
- [ ] **Drag Overlay Enhancement**: Improve drag overlay visual feedback with better shadow and rotation effects

#### Empty States
- [ ] **Actionable Empty States**: Replace "No applications" text with actionable empty states:
  - Message: "No applications in this stage. Drag one here or create a new application."
  - Include quick action button in empty columns (e.g., "Add Application")
  - Add helpful illustrations or icons for visual interest

#### Card Information Enhancement
- [ ] **Candidate Avatars**: Show candidate avatar/initials on application cards for better visual identification
- [ ] **Attention Indicators**: Add small indicator badges for applications that need attention:
  - SLA risk warnings
  - Unread comments
  - Pending actions
- [ ] **Job Department Badge**: Show job department/team as a small badge on cards for quick context

#### Bulk Actions Enhancement
- [ ] **Keyboard Support**: Add keyboard shortcuts for bulk operations:
  - `Cmd+A` / `Ctrl+A` to select all visible applications
  - `Esc` to cancel selection mode
  - Arrow keys for navigation when in selection mode
- [ ] **Confirmation Dialogs**: Add confirmation dialog for bulk transitions showing:
  - Number of applications being moved
  - Target state
  - Any warnings (e.g., applications in different states)
- [ ] **Undo/Redo**: Implement undo/redo functionality for bulk operations with toast notification

#### Search and Filters
- [ ] **Advanced Filters**: Add advanced filter panel with:
  - Date range picker (applied date, state entered date)
  - Status filter (active, terminal, all)
  - Risk level filter (LOW, MEDIUM, HIGH)
  - Source filter
  - SLA status filter (on-time, warning, critical)
- [ ] **Saved Filter Presets**: Allow users to save and name filter combinations for quick access
- [ ] **Active Filter Badge**: Show count badge on filter icon indicating number of active filters
- [ ] **Filter Chips**: Display active filters as removable chips above the board for easy management

#### Multi-Funnel Experience
- [ ] **Funnel Selection UI**: When "All Jobs" is selected and multiple funnels detected:
  - Show funnel selector dropdown to switch between funnels
  - Display funnel name/description in the warning banner
  - Allow quick switching without changing job filter

---

### 4. General UX Improvements

#### Loading States
- [ ] **Skeleton Screens**: Replace generic spinners with skeleton screens that match the content structure:
  - Skeleton cards for pipeline board
  - Skeleton rows for list views
  - Skeleton charts for dashboard
- [ ] **Progress Indicators**: Show progress for long-running operations:
  - Progress bar for bulk transitions
  - Percentage complete for bulk uploads
  - Estimated time remaining where applicable
- [ ] **Optimistic Updates**: Implement optimistic UI updates for:
  - State transitions (show card in new column immediately)
  - Bulk operations (update UI before API confirmation)
  - Form submissions (show success state immediately)

#### Error Handling
- [ ] **Toast Notifications**: Replace all `alert()` calls with toast notification system:
  - Success toasts (green) for successful operations
  - Error toasts (red) for failures
  - Warning toasts (amber) for warnings
  - Info toasts (blue) for informational messages
  - Auto-dismiss with configurable duration
  - Stack multiple toasts vertically
- [ ] **Retry Mechanisms**: Add retry buttons in error states:
  - "Retry" button on failed API calls
  - "Try Again" for failed transitions
  - Exponential backoff for automatic retries
- [ ] **Inline Validation**: Replace alert-based validation with inline error messages:
  - Show errors below form fields
  - Highlight invalid fields with red border
  - Show error summary at top of forms
  - Real-time validation feedback

#### Accessibility
- [ ] **ARIA Labels**: Add comprehensive ARIA labels to all interactive elements:
  - Buttons: `aria-label` with descriptive text
  - Form fields: `aria-describedby` linking to help text
  - Navigation: `aria-current="page"` for active routes
  - Modals: `aria-labelledby` and `aria-describedby`
- [ ] **Keyboard Navigation**: Ensure full keyboard navigation support:
  - Tab order follows visual flow
  - Enter/Space to activate buttons
  - Arrow keys for list navigation
  - Escape to close modals/dropdowns
  - Focus trap in modals
- [ ] **Focus Indicators**: Improve focus indicators to meet WCAG standards:
  - Visible focus rings on all interactive elements
  - High contrast focus indicators
  - Skip links for main content
- [ ] **Screen Reader Support**: Add proper announcements for:
  - State changes (e.g., "Application moved to Interview stage")
  - Loading states ("Loading applications...")
  - Error messages ("Error: Failed to load data")
  - Success messages ("Application created successfully")

#### Performance Optimizations
- [ ] **Virtual Scrolling**: Implement virtual scrolling for long lists:
  - Pipeline list view with virtual scrolling
  - Candidate table with virtual rows
  - Job grid with virtual items
- [ ] **Pagination/Infinite Scroll**: Add pagination or infinite scroll for large datasets:
  - Configurable page size (25, 50, 100)
  - "Load more" button for infinite scroll option
  - URL-based pagination state
- [ ] **Debounced Search**: Add debouncing to search inputs:
  - 300ms delay before triggering search
  - Cancel previous requests on new input
  - Show loading indicator during search

#### User Preferences
- [ ] **Default View Settings**: Allow users to set preferences:
  - Default view mode (Kanban vs List)
  - Default filters to apply on page load
  - Items per page preference
- [ ] **Notification Preferences**: Add notification settings:
  - Email notifications toggle
  - Browser notification permissions
  - Notification categories (SLA alerts, comments, transitions)
- [ ] **Keyboard Shortcuts**: Add customizable keyboard shortcuts:
  - Global search (`Cmd+K` / `Ctrl+K`)
  - Quick navigation (`Cmd+1-9` for nav items)
  - Quick actions (`N` for new, `/` for search)
  - Settings page to customize shortcuts

---

### 5. Visual Design Improvements

#### Color and Contrast
- [ ] **WCAG AA Compliance**: Ensure all text meets WCAG AA contrast ratios:
  - Regular text: 4.5:1 contrast ratio
  - Large text: 3:1 contrast ratio
  - Interactive elements: 3:1 contrast ratio
  - Audit all color combinations (text on backgrounds)
- [ ] **Depth and Hierarchy**: Add subtle shadows/depth to improve visual hierarchy:
  - Cards: Subtle shadow on hover
  - Modals: Stronger shadow for elevation
  - Dropdowns: Shadow to indicate floating
  - Buttons: Subtle shadow for primary actions
- [ ] **Design Token System**: Implement consistent design token system:
  - Spacing scale (4px, 8px, 12px, 16px, 24px, 32px, 48px, 64px)
  - Color palette with semantic naming (primary, secondary, success, error, warning)
  - Typography scale (font sizes, line heights, weights)
  - Border radius scale
  - Shadow scale

#### Typography
- [ ] **Typography Hierarchy**: Establish clear typographic hierarchy:
  - H1: 32px, semibold (page titles)
  - H2: 24px, semibold (section headers)
  - H3: 20px, medium (subsection headers)
  - Body: 16px, regular (default text)
  - Small: 14px, regular (captions, metadata)
  - Tiny: 12px, regular (labels, badges)
- [ ] **Consistent Font Weights**: Use consistent font weight scale:
  - Regular (400) for body text
  - Medium (500) for emphasis
  - Semibold (600) for headings
  - Bold (700) sparingly for strong emphasis
- [ ] **Text Truncation**: Add consistent text truncation with tooltips:
  - Truncate long candidate names with ellipsis
  - Show full text on hover via tooltip
  - Truncate long job titles
  - Truncate long notes/comments

#### Icons and Imagery
- [ ] **Contextual Icons**: Add more contextual icons throughout:
  - Status icons (checkmark, clock, alert)
  - Action icons (edit, delete, duplicate)
  - Navigation icons (consistent with Lucide React)
- [ ] **Icon Consistency**: Ensure consistent icon usage:
  - Standard icon size: 16px (small), 20px (medium), 24px (large)
  - Consistent stroke width (1.5px for outline style)
  - Consistent spacing around icons (4px gap)
- [ ] **Empty State Illustrations**: Add illustrations for empty states:
  - Empty pipeline: Illustration of empty board
  - No search results: Illustration with search icon
  - No candidates: Illustration with person icon
  - Use consistent illustration style (line art, minimal)

#### Component Polish
- [ ] **Button States**: Improve button visual states:
  - Hover: Slight scale or color change
  - Active: Pressed state with shadow reduction
  - Disabled: Reduced opacity with cursor-not-allowed
  - Loading: Spinner with disabled state
- [ ] **Form Field States**: Enhance form field visual feedback:
  - Focus: Border color change + ring
  - Error: Red border + error icon + message
  - Success: Green border + checkmark icon
  - Disabled: Gray background + reduced opacity
- [ ] **Card Interactions**: Improve card hover/focus states:
  - Hover: Subtle lift with shadow increase
  - Focus: Visible focus ring
  - Selected: Border highlight + background tint
  - Active: Pressed state for clickable cards

#### Responsive Design Refinements
- [ ] **Mobile Touch Targets**: Ensure all interactive elements meet minimum touch target size:
  - Minimum 44x44px for all buttons
  - Minimum 44px height for form inputs
  - Adequate spacing between touch targets (8px minimum)
- [ ] **Tablet Optimization**: Optimize layouts for tablet sizes:
  - Sidebar can remain visible on larger tablets
  - Cards can show in 2-column grid on tablets
  - Modals can be larger on tablets
- [ ] **Breakpoint Consistency**: Use consistent breakpoints:
  - Mobile: < 640px
  - Tablet: 640px - 1024px
  - Desktop: > 1024px
  - Large Desktop: > 1280px

---

### 6. Table Column Visibility & Sorting (v0.16 Planned)

**Overview**: Enable users to customize which columns are visible in table views and sort by any column. This is critical for power users who need flexible data views.

#### Phase 1: DataTable Configuration System
- [ ] **ColumnConfig Interface**: Define column configuration with visibility, sort, and display options
  ```typescript
  interface ColumnConfig<T> {
    id: string;
    header: string;
    accessor: keyof T | ((row: T) => unknown);
    sortable?: boolean;
    defaultVisible?: boolean;
    width?: number | 'auto';
    align?: 'left' | 'center' | 'right';
    render?: (value: unknown, row: T) => React.ReactNode;
    sortFn?: (a: T, b: T) => number;  // Custom sort function
  }
  ```
- [ ] **useTableState Hook**: Manage column visibility, sort state, and persistence
  ```typescript
  interface UseTableStateOptions {
    tableId: string;  // For localStorage persistence
    columns: ColumnConfig[];
    defaultSort?: { columnId: string; direction: 'asc' | 'desc' };
  }

  function useTableState(options: UseTableStateOptions): {
    visibleColumns: ColumnConfig[];
    hiddenColumns: ColumnConfig[];
    sortState: { columnId: string; direction: 'asc' | 'desc' } | null;
    toggleColumnVisibility: (columnId: string) => void;
    setSort: (columnId: string, direction?: 'asc' | 'desc') => void;
    resetToDefaults: () => void;
  }
  ```

#### Phase 2: Column Visibility UI
- [ ] **ColumnVisibilityDropdown Component**: Multi-select dropdown to toggle columns
  - Checkboxes for each available column
  - "Show All" / "Reset to Defaults" buttons
  - Search/filter for tables with many columns
  - Drag-and-drop column reordering (optional)
- [ ] **Integration Points**:
  - CandidatesPage table
  - PipelineListView table
  - JobsPage table (if converted to table view)
  - RequisitionsPage list

#### Phase 3: Enhanced Sorting
- [ ] **Multi-Column Sort**: Support sorting by primary and secondary columns
- [ ] **Sort Type Detection**: Automatic handling of:
  - Text (alphabetical, case-insensitive)
  - Numbers (numeric comparison)
  - Dates (chronological)
  - Custom (user-defined sort functions)
- [ ] **Sort Indicators**: Clear visual feedback for sort direction
- [ ] **URL State**: Persist sort state in URL query params for bookmarkability

#### Phase 4: Table Migration
- [ ] **CandidatesPage**: Migrate to new DataTable with column visibility
- [ ] **PipelineListView**: Add column configuration
- [ ] **JobsPage**: Consider table view option with column visibility
- [ ] **RequisitionsPage**: Ensure sortable columns

#### Phase 5: Persistence
- [ ] **localStorage**: Save column preferences per table per user
- [ ] **URL State**: Sort and visible columns in query params
- [ ] **User Preferences API** (future): Server-side preference storage

#### Files to Create
| File | Purpose |
|------|---------|
| `core/components/DataTable/DataTable.tsx` | Generic table component |
| `core/components/DataTable/ColumnVisibilityDropdown.tsx` | Column toggle UI |
| `core/components/DataTable/SortableHeader.tsx` | Sortable column header |
| `core/hooks/useTableState.ts` | Table state management |
| `core/types/table.ts` | ColumnConfig and related types |

#### Files to Modify
| File | Change |
|------|--------|
| `domains/ats/pages/CandidatesPage.tsx` | Use new DataTable |
| `domains/ats/components/pipeline/PipelineListView.tsx` | Use new DataTable |
| `domains/ats/pages/JobsPage.tsx` | Add table view option |

---

### Priority Implementation Order

#### High Priority (Immediate Impact)
1. Replace `alert()` with toast notifications
2. Add loading skeletons instead of spinners
3. Improve empty states with actionable content
4. Add keyboard navigation support
5. Improve mobile touch targets
6. Add ARIA labels for accessibility

#### Medium Priority (Enhanced UX)
1. Add advanced filters and saved presets
2. Implement virtual scrolling for performance
3. Add notification dropdown functionality
4. Improve error handling with inline errors
5. Add candidate avatars to cards
6. Implement optimistic updates

#### Low Priority (Polish & Advanced Features)
1. Dark mode support
2. Customizable keyboard shortcuts
3. Advanced animations and transitions
4. Design token system implementation
5. Empty state illustrations
6. Real-time collaboration features

---

### 7. Role-Based Access Control (RBAC) UI (v0.16 Planned)

**Overview**: Full role management UI enabling admins to create custom roles with granular permissions at entity and field levels. Supports both system-wide permissions and configurable field-level access control.

**Aligned with**: Backend RBAC implementation (see `design_docs/backend_progress.MD`)

#### Phase 1: TypeScript Types & API Client

**New Types** (`core/types/rbac.ts`):
```typescript
// Permission types
export type PermissionAction = 'view' | 'create' | 'edit' | 'delete' | 'transition';

export interface Permission {
  id: string;
  entity_type: string;        // e.g., 'ATS.Candidate', 'ATS.Job', '*' for all
  action: PermissionAction;
  resource_scope?: string;    // Optional: specific resource IDs or patterns
}

export interface FieldPermission {
  id: string;
  entity_type: string;
  field_name: string;
  can_view: boolean;
  can_edit: boolean;
  mask_value: boolean;        // Show masked value (e.g., "****@email.com")
}

// Role definition
export interface Role {
  id: string;
  organization_id: string;
  name: string;               // Unique within org, slug format
  display_name: string;
  description?: string;
  is_system: boolean;         // System roles cannot be deleted
  priority: number;           // Higher priority wins in conflicts
  permissions: Permission[];
  field_permissions: FieldPermission[];
  created_at: string;
  updated_at: string;
}

export interface RoleCreateRequest {
  name: string;
  display_name: string;
  description?: string;
  permissions: Omit<Permission, 'id'>[];
  field_permissions?: Omit<FieldPermission, 'id'>[];
}

export interface RoleUpdateRequest {
  display_name?: string;
  description?: string;
  permissions?: Omit<Permission, 'id'>[];
  field_permissions?: Omit<FieldPermission, 'id'>[];
  priority?: number;
}

// User role assignment
export interface UserRole {
  user_id: string;
  role_id: string;
  role: Role;
  assigned_at: string;
  assigned_by?: string;
}
```

**API Client** (`core/services/api.ts`):
```typescript
roles: {
  list: () => GET('/roles'),
  get: (id: string) => GET(`/roles/${id}`),
  create: (data: RoleCreateRequest) => POST('/roles', data),
  update: (id: string, data: RoleUpdateRequest) => PUT(`/roles/${id}`, data),
  delete: (id: string) => DELETE(`/roles/${id}`),
  duplicate: (id: string, newName: string) => POST(`/roles/${id}/duplicate`, { name: newName }),
},
userRoles: {
  list: (userId: string) => GET(`/users/${userId}/roles`),
  assign: (userId: string, roleId: string) => POST(`/users/${userId}/roles`, { role_id: roleId }),
  remove: (userId: string, roleId: string) => DELETE(`/users/${userId}/roles/${roleId}`),
}
```

#### Phase 2: usePermissions Hook

**Hook Implementation** (`core/hooks/usePermissions.ts`):
```typescript
interface UsePermissionsResult {
  // Current user's effective permissions
  permissions: Permission[];
  fieldPermissions: FieldPermission[];

  // Permission checks
  can: (action: PermissionAction, entityType: string, resourceId?: string) => boolean;
  canViewField: (entityType: string, fieldName: string) => boolean;
  canEditField: (entityType: string, fieldName: string) => boolean;
  shouldMaskField: (entityType: string, fieldName: string) => boolean;

  // Bulk checks for rendering
  getFieldPermissions: (entityType: string) => Map<string, FieldPermission>;
  filterVisibleFields: (entityType: string, fields: FormField[]) => FormField[];

  // Loading state
  loading: boolean;
  error: string | null;
}

function usePermissions(): UsePermissionsResult;
```

**Usage Pattern**:
```typescript
// In components
const { can, canEditField, shouldMaskField } = usePermissions();

// Check entity-level permission
if (can('edit', 'ATS.Candidate')) {
  // Show edit button
}

// Check field-level permission
if (canEditField('ATS.Candidate', 'salary_expectation')) {
  // Show editable field
} else if (shouldMaskField('ATS.Candidate', 'salary_expectation')) {
  // Show masked value
}
```

#### Phase 3: Settings > Roles Tab UI

**RolesTab Component** (`domains/ats/components/settings/RolesTab.tsx`):

**Role List View**:
- Table showing all roles with columns: Name, Type (System/Custom), Users Count, Last Modified
- System roles (admin, recruiter, hiring_manager, viewer) marked with badge, cannot be deleted
- Custom roles can be edited, duplicated, deleted
- "Create Role" button opens RoleEditor modal
- Click row to open RoleEditor in edit mode

**RoleEditor Modal** (`domains/ats/components/settings/RoleEditor.tsx`):

Step-based wizard with sections:
1. **Basics Tab**:
   - Role name (slug, auto-generated from display name)
   - Display name (human-readable)
   - Description (optional)
   - Priority (numeric, for permission conflict resolution)

2. **Entity Permissions Tab**:
   - Entity type selector (all entity types from `useEntityTypes`)
   - Permission matrix grid:
     ```
     Entity Type       | View | Create | Edit | Delete | Transition
     ------------------|------|--------|------|--------|----------
     ATS.Candidate     |  ✓   |   ✓    |  ✓   |   ✗    |    -
     ATS.Job           |  ✓   |   ✗    |  ✗   |   ✗    |    -
     ATS.Application   |  ✓   |   ✓    |  ✓   |   ✗    |    ✓
     ```
   - Bulk actions: "Grant All", "View Only", "No Access"

3. **Field Permissions Tab**:
   - Entity type selector dropdown
   - When entity selected, shows all fields from FormSchema
   - Per-field permission matrix:
     ```
     Field Name        | Visible | Editable | Masked
     ------------------|---------|----------|-------
     full_name         |    ✓    |    ✓     |   ✗
     email             |    ✓    |    ✓     |   ✗
     phone             |    ✓    |    ✓     |   ✗
     salary_expectation|    ✓    |    ✗     |   ✓
     ssn               |    ✗    |    ✗     |   ✗
     ```
   - Quick filters: "Show configured only", "Show all fields"
   - Template buttons: "Copy from Role..." dropdown

4. **Preview Tab**:
   - Summary of all permissions configured
   - "Test as this role" preview (optional, shows what UI would look like)
   - Validation warnings (e.g., "No view permission but edit permission granted")

#### Phase 4: User Role Assignment UI

**UsersTab Enhancement** (`domains/ats/components/settings/UsersTab.tsx`):
- Add "Role" column to users table showing assigned role
- Click role badge opens role assignment dropdown
- Role assignment dropdown:
  - List of available roles with descriptions
  - Current role highlighted
  - Select to change role
  - Changes saved immediately with confirmation toast

**UserRoleAssignment Component** (`domains/ats/components/settings/UserRoleAssignment.tsx`):
- Dropdown/popover for changing user role
- Shows role name, description, permission summary
- Confirmation dialog for role changes
- Supports assigning multiple roles (if enabled)

#### Phase 5: Permission-Aware UI Integration

**DynamicFormFields Enhancement**:
- Accept `fieldPermissions` prop from `usePermissions`
- Filter out fields where `can_view: false`
- Render read-only fields where `can_view: true, can_edit: false`
- Apply masking for fields where `mask_value: true`

**ApplicationDetail Enhancement**:
- Hide "Edit" button if `!can('edit', 'ATS.Application')`
- Hide "Schedule Interview" if `!can('create', 'ATS.Interview')`
- Hide transition buttons if `!can('transition', 'ATS.Application')`

**CandidateInfoSection Enhancement**:
- Filter visible fields based on field permissions
- Mask sensitive fields (e.g., show "***" for phone)

**PipelineBoard Enhancement**:
- Disable drag-drop if `!can('transition', 'ATS.Application')`
- Hide "Add Application" if `!can('create', 'ATS.Application')`
- Show read-only badge if user has view-only access

**Navigation Enhancement**:
- Hide nav items for entity types user cannot view
- Show count badges only for accessible entities

#### Phase 6: Permission Denied States

**PermissionDenied Component** (`core/components/PermissionDenied.tsx`):
- Friendly "Access Denied" message with icon
- Explanation of required permission
- "Request Access" button (optional, sends notification to admin)

**Usage**:
```tsx
if (!can('view', 'ATS.Candidate')) {
  return <PermissionDenied entityType="ATS.Candidate" action="view" />;
}
```

**Protected Components Pattern**:
```tsx
// Wrapper component for permission-gated sections
<PermissionGate entityType="ATS.Candidate" action="edit">
  <EditCandidateButton />
</PermissionGate>
```

#### Files to Create

| File | Purpose |
|------|---------|
| `core/types/rbac.ts` | RBAC TypeScript types |
| `core/hooks/usePermissions.ts` | Permission checking hook |
| `core/hooks/useRoles.ts` | Role management hook |
| `core/components/PermissionDenied.tsx` | Access denied component |
| `core/components/PermissionGate.tsx` | Permission-based rendering gate |
| `domains/ats/components/settings/RolesTab.tsx` | Role management tab |
| `domains/ats/components/settings/RoleEditor.tsx` | Role create/edit modal |
| `domains/ats/components/settings/RolePermissionMatrix.tsx` | Entity permission grid |
| `domains/ats/components/settings/FieldPermissionEditor.tsx` | Field permission config |
| `domains/ats/components/settings/UserRoleAssignment.tsx` | User role dropdown |

#### Files to Modify

| File | Change |
|------|--------|
| `core/services/api.ts` | Add roles and userRoles API methods |
| `core/auth/AuthContext.tsx` | Fetch user permissions on login |
| `core/types/index.ts` | Export RBAC types |
| `domains/ats/components/DynamicFormFields.tsx` | Add permission-aware rendering |
| `domains/ats/components/ApplicationDetail.tsx` | Gate actions by permission |
| `domains/ats/components/CandidateInfoSection.tsx` | Field masking support |
| `domains/ats/components/pipeline/PipelineBoard.tsx` | Permission-aware drag-drop |
| `domains/ats/components/settings/SettingsPage.tsx` | Add Roles tab |
| `domains/ats/components/settings/UsersTab.tsx` | Role assignment column |
| `layouts/AppLayout.tsx` | Permission-aware navigation |

#### Implementation Order

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| 1 | Types & API client | Backend RBAC API |
| 2 | usePermissions hook | Phase 1 |
| 3 | RolesTab & RoleEditor | Phase 1 |
| 4 | User role assignment | Phase 3 |
| 5 | Permission-aware UI | Phase 2, 4 |
| 6 | Permission denied states | Phase 2 |

#### UI Mockups

**Role List View**:
```
┌─────────────────────────────────────────────────────────────────┐
│ Settings > Roles                            [+ Create Role]     │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Role Name        │ Type    │ Users │ Modified    │ Actions │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ Admin            │ System  │ 2     │ -           │ View    │ │
│ │ Recruiter        │ System  │ 5     │ -           │ View    │ │
│ │ Hiring Manager   │ System  │ 8     │ -           │ View    │ │
│ │ Viewer           │ System  │ 3     │ -           │ View    │ │
│ │ ────────────────────────────────────────────────────────── │ │
│ │ Senior Recruiter │ Custom  │ 2     │ Jan 15      │ ⋮       │ │
│ │ External Review  │ Custom  │ 4     │ Jan 12      │ ⋮       │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Role Editor - Field Permissions**:
```
┌─────────────────────────────────────────────────────────────────┐
│ Edit Role: Senior Recruiter                              [Save] │
├─────────────────────────────────────────────────────────────────┤
│ [Basics] [Entity Permissions] [Field Permissions] [Preview]     │
├─────────────────────────────────────────────────────────────────┤
│ Entity Type: [ATS.Candidate ▼]                                  │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Field              │ Visible │ Editable │ Masked │          │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ full_name          │   ☑     │    ☑     │   ☐    │          │ │
│ │ email              │   ☑     │    ☑     │   ☐    │          │ │
│ │ phone              │   ☑     │    ☑     │   ☐    │          │ │
│ │ salary_expectation │   ☑     │    ☐     │   ☑    │          │ │
│ │ ssn                │   ☐     │    ☐     │   ☐    │          │ │
│ │ internal_notes     │   ☐     │    ☐     │   ☐    │          │ │
│ │ background_check   │   ☑     │    ☐     │   ☐    │          │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ [Copy from Role...▼]  [Reset to Defaults]                       │
└─────────────────────────────────────────────────────────────────┘
```
