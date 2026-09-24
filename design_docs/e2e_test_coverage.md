# E2E Test Coverage — Flowtuple Platform

> **243 automated browser tests** across 16 spec files.
> Run time: ~2 minutes. Tool: Playwright + Chromium.

---

## How to Run

```bash
cd frontend

# Run all tests
npm run test:e2e

# Run with visible browser
npm run test:e2e:headed

# Interactive Playwright UI
npm run test:e2e:ui

# Run specific spec file
npx playwright test 01-smoke.spec.ts

# Run by tag
npx playwright test --grep @smoke
npx playwright test --grep @critical
npx playwright test --grep @regression

# View last report
npx playwright show-report
```

**Prerequisites:**
1. Backend running on `:8001`
2. Frontend running on `:5173` (auto-starts if not running)
3. `.env.test` with test credentials (copy from `.env.test.example`)

---

## Test Sequence (Execution Order)

### Phase 0 — Setup (runs once before all tests)

| # | Test | What it does |
|---|------|-------------|
| 1 | Authenticate as admin | Logs in via UI, saves browser session for reuse |
| 2 | Authenticate as superadmin | Same for superadmin role |
| 3 | Seed test workflow data | Creates E2ETestJob entity type, workflow (3 states, 3 transitions), form config, test entity via API |

---

### Phase 1 — Smoke Tests (`01-smoke`)

> **Purpose:** Verify the app loads and basic auth works. If these fail, nothing else will work.

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Authenticated user sees main layout | @smoke | Navigation sidebar visible after login |
| 2 | Unauthenticated visit shows login or public page | @smoke | Redirects to `/login` or `/workflows` |

---

### Phase 2 — Permissions (`02-permissions`)

> **Purpose:** Verify role-based access control. Admin vs Superadmin see different things.

| # | Test | Tag | Role | Expected Result |
|---|------|-----|------|----------------|
| 1 | Admin can access Settings page | @critical | admin | Settings page loads with search bar |
| 2 | Admin does NOT see Organizations tab | @critical | admin | Organizations tab hidden in Settings sidebar |
| 3 | Admin sees navigation sidebar | @smoke | admin | Sidebar navigation present |
| 4 | Superadmin can access Settings page | @critical | superadmin | Settings page loads |
| 5 | Superadmin sees Organizations tab | @critical | superadmin | Organizations visible under GOVERN section |
| 6 | Superadmin can navigate to Organizations | @critical | superadmin | Click Organizations → page loads with breadcrumb |
| 7 | Superadmin sees Settings in sidebar | @smoke | superadmin | Settings link visible in nav |
| 8 | Superadmin sees user info with role badge | @smoke | superadmin | "Bootstrap Super Admin" visible at bottom |

---

### Phase 3 — Workflow & Pipeline (`03-workflow-pipeline`)

> **Purpose:** Core product flow — workflows exist, pipeline loads, entity creation dialog works.

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Workflows page loads and shows seeded workflow | @smoke | "E2E Test Workflow" visible |
| 2 | Records page loads | @smoke | `/records` renders |
| 3 | Can navigate from workflows to pipeline board | @critical | Click workflow → URL changes to `/pipeline/` |
| 4 | Pipeline board shows state columns | @critical | OPEN, IN_REVIEW, CLOSED columns visible |
| 5 | Add entity button visible on pipeline | @critical | "Add E2etestjob" button in header |
| 6 | Clicking add entity opens creation dialog | @critical | Dialog with form fields appears |
| 7 | Entity creation dialog has save and cancel | @critical | Save + Cancel buttons visible |
| 8 | Entity creation dialog can be dismissed | @regression | Cancel → dialog closes |
| 9 | Pipeline board shows view toggle options | @smoke | Board/Table toggle visible |
| 10 | Pipeline shows workflow name in header | @smoke | "E2E Test Workflow" in page header |

---

### Phase 4 — Form Configuration (`04-form-configuration`)

> **Purpose:** Form configuration in Settings and entity creation validation.

**Form Configuration (Settings → Forms):**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Forms tab loads in Settings | @smoke | "Form Configuration" heading visible |
| 2 | New Form button visible | @smoke | "+ New Form" button in header |
| 3 | New Form dialog has required fields | @critical | Entity type select + display name input + Create Form button |
| 4 | New Form dialog can be dismissed | @regression | Cancel → dialog closes |

**Entity Creation Dialog (Pipeline → Add):**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 5 | Add dialog shows form fields | @critical | Unique Name, Title, Status Note visible |
| 6 | Add dialog shows due date field | @smoke | "Due date" label visible |
| 7 | Add dialog has save and cancel buttons | @smoke | Save + Cancel in footer |
| 8 | Save disabled when required fields empty | @critical | Save button grayed out |
| 9 | Save enables after filling required fields | @critical | Save becomes clickable after filling identifier + title |
| 10 | Cancel closes dialog without side effects | @regression | Cancel → back to pipeline |

**Records Page:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 11 | Records page shows E2ETestJob entity type | @smoke | Entity type card visible |
| 12 | Clicking entity type shows records table | @critical | URL changes to `/records/` |

---

### Phase 5 — Navigation & Views (`05-navigation-views`)

> **Purpose:** Dashboard, pipeline views, sidebar — screens users interact with daily.

**Dashboard:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Dashboard page loads | @smoke | Page renders without error |

**Pipeline Board:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 2 | Board view is the default | @smoke | Board toggle is active state |
| 3 | Can switch to Table view | @critical | Click "Table" → table with rows appears |
| 4 | Can switch to Calendar view | @critical | Click "Calendar" → calendar renders |
| 5 | Can switch back to Board from Table | @regression | Navigate to pipeline URL → board loads |
| 6 | Show Closed toggle present | @smoke | "Show Closed" button visible |
| 7 | Export button present | @smoke | "Export" button in header |

**Pipeline Table:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 8 | Table view shows column headers | @critical | Table element with headers visible |
| 9 | Table view has search/filter | @smoke | Search input or filter button visible |

**Sidebar:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 10 | Sidebar shows all main nav items | @smoke | Dashboard, Workflows, Records buttons visible |
| 11 | Sidebar can collapse and expand | @regression | Toggle button works |
| 12 | Workflows sidebar expands to show list | @critical | Click Workflows → workflow items appear |

---

### Phase 6 — Settings Tabs (`06-settings-tabs`)

> **Purpose:** Every settings tab loads without errors. Catches broken imports, API failures, render crashes.

| # | Tab | Section | Tag |
|---|-----|---------|-----|
| 1 | Funnels | BUILD | @smoke |
| 2 | Automations | BUILD | @smoke |
| 3 | Entities | BUILD | @critical |
| 4 | Email Templates | BUILD | @smoke |
| 5 | Agents | RUN | @smoke |
| 6 | MCP Tools | RUN | @smoke |
| 7 | Agent Runs | RUN | @smoke |
| 8 | Agent Traces | RUN | @smoke |
| 9 | API Coverage | RUN | @smoke |
| 10 | Documents | DATA | @smoke |
| 11 | Integrations | DATA | @smoke |
| 12 | Connectors | DATA | @smoke |
| 13 | Users | GOVERN | @critical |
| 14 | Roles | GOVERN | @smoke |
| 15 | Branding | GOVERN | @smoke |
| 16 | Display | GOVERN | @smoke |
| 17 | Column Labels | GOVERN | @smoke |
| 18 | Global Filter | GOVERN | @smoke |
| 19 | App Labels | GOVERN | @smoke |

---

### Phase 7 — Entity Lifecycle (`07-entity-lifecycle`)

> **Purpose:** The heart of the product — creating records, viewing details, and moving through workflow states.

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Can create entity — dialog closes on save | @critical | Fill identifier + title → Save → dialog disappears |
| 2 | Created entity appears in table view | @critical | Switch to Table → search → entity row visible |
| 3 | Clicking entity opens slide-over with Move to | @critical | Click row → URL has `?entity=` → "Move to" button visible |
| 4 | Slide-over shows field data | @critical | "Title" label visible in detail panel |
| 5 | Slide-over has Edit button | @critical | Edit button in details section |
| 6 | Edit mode shows Save and Cancel | @critical | Click Edit → Save + Cancel appear |
| 7 | Move to dropdown shows Start Review | @critical | Click "Move to" → "Start Review" menu item visible |
| 8 | Executing transition succeeds | @critical | Click "Start Review" → Move to button re-enables |
| 9 | IN_REVIEW shows Close transition | @critical | After transition → "Close" available in dropdown |
| 10 | Slide-over closes with Escape | @regression | Press Escape → URL no longer has `?entity=` |

---

### Phase 8 — Form Builder (`08-form-builder`)

> **Purpose:** Deeper form configuration and entity detail tabs.

**Form Builder:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Add field opens modal with label input | @critical | "e.g., Custom Field" placeholder visible |
| 2 | Can add a text field | @critical | Fill label → Add Field → field appears in editor |
| 3 | Field type dropdown has all types | @smoke | Text, Email, Phone, Integer, Currency, Select, Checkbox, URL, Table, Auto Number |
| 4 | Cancel closes modal without saving | @regression | Cancel → placeholder hidden |
| 5 | Edit JSON button visible | @smoke | "Edit JSON" button in form editor |
| 6 | Add Picklist button visible | @smoke | "Add Picklist" text visible |

**Entity Detail Tabs:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 7 | Details tab visible | @critical | "Details" button/tab visible |
| 8 | Activity tab visible | @smoke | "Activity" text visible |
| 9 | Activity tab shows timeline | @smoke | Click Activity → content loads |
| 10 | Comments tab visible | @critical | "Comments" text visible |
| 11 | Comments tab can be opened | @critical | Click Comments → content area loads |
| 12 | Documents section visible | @smoke | "Documents" text visible |

---

### Phase 9 — Auth, Dashboard & Users (`09-auth-dashboard-users`)

> **Purpose:** Authentication pages, dashboard widgets, and user/role management.

**Auth Pages (no login needed):**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Login page has email + password fields | @smoke | Email label + password textbox visible |
| 2 | Login page has Sign in button | @smoke | "Sign in" exact button visible |
| 3 | Login page has Google OAuth button | @smoke | "Sign in with Google" button |
| 4 | Login page has Microsoft OAuth button | @smoke | "Sign in with Microsoft" button |
| 5 | Login page has Forgot password link | @smoke | "Forgot password?" text visible |
| 6 | Forgot password page loads | @smoke | Email input visible on `/forgot-password` |
| 7 | Reset password page loads | @smoke | `/reset-password` renders |
| 8 | Accept invite page loads | @smoke | `/accept-invite` renders |

**Dashboard:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 9 | Active Entities widget visible | @critical | "Active Entities" text + count number |
| 10 | SLA Breaches widget visible | @critical | "SLA Breaches" text |
| 11 | Pipeline by State widget visible | @smoke | "Pipeline by State" text |
| 12 | Refresh button present | @smoke | Refresh button clickable |
| 13 | Edit button present | @smoke | Edit button in header |
| 14 | Time range filters visible | @critical | All time, Today, This week, This month |
| 15 | Clicking time range filter works | @critical | Click "Today" → filter active |
| 16 | Edit mode shows Editing badge + Add widget | @regression | Click Edit → "Editing" badge + "Add widget" |

**Users Management:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 17 | Users tab shows user list | @critical | Admin user email visible |
| 18 | Invite User button visible | @critical | "Invite User" button |
| 19 | Invite User dialog opens | @critical | Click → email input visible |
| 20 | Invite User dialog can be dismissed | @regression | Cancel → dialog closes |

**Roles Management:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 21 | Roles tab loads | @critical | Breadcrumb visible |
| 22 | New Role button visible | @critical | "New Role" button |
| 23 | New Role opens role editor | @critical | "Create Role" or "New Role" heading |

---

### Phase 10 — Documents & Notifications (`10-documents-notifications`)

> **Purpose:** Document management, pipeline search, connectors, email templates, notifications, public forms.

**Documents:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Entity detail has Documents section | @smoke | "Documents" text visible in slide-over |
| 2 | Upload button visible | @critical | Upload button in documents section |
| 3 | Upload dropdown shows options | @critical | Click upload → document type selector |

**Pipeline Search & Filter:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 4 | Table view has search input | @critical | Search placeholder visible |
| 5 | Search filters entities | @critical | Type text → table rows filter |
| 6 | Clearing search shows all entities | @regression | Clear input → all rows return |
| 7 | State filter dropdown exists | @smoke | Filter select visible |

**Connectors:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 8 | Tab loads | @smoke | Breadcrumb visible |
| 9 | New Connector button visible | @critical | "New Connector" button |
| 10 | New Connector opens form | @critical | Click → name input visible |

**Email Templates:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 11 | Tab loads | @smoke | Breadcrumb visible |
| 12 | New Template button visible | @critical | "New Template" button/text |
| 13 | Search input exists | @smoke | Search placeholder visible |

**Integrations:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 14 | Tab loads | @smoke | Breadcrumb visible |

**Notifications:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 15 | Bell icon visible in top bar | @smoke | Bell SVG icon in header |
| 16 | Clicking bell opens dropdown | @critical | "No notifications" or notification list |

**Public Forms:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 17 | Invalid token doesn't crash | @smoke | Page renders (error or form) |
| 18 | Powered by FlowTuple branding | @smoke | Branding text visible |

---

### Phase 11 — Entity Details (`11-entity-details`)

> **Purpose:** In-depth entity creation, editing, and detail panel sections.

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Add dialog shows identifier as required | @critical | "Unique Name" label with asterisk |
| 2 | Add dialog shows Due date picker | @smoke | "Due date" label visible |
| 3 | Add dialog shows Default form (Title + Status Note) | @critical | "Default" heading + both field labels |
| 4 | Add dialog shows All Fields form when scrolled | @critical | "All Fields" section visible after scroll |
| 5 | Save disabled when identifier empty | @critical | Save button grayed out |
| 6 | Save disabled when required Title empty | @critical | Fill identifier only → Save still disabled |
| 7 | Can create entity with identifier + title | @critical | Fill both → Save → entity in table |
| 8 | Edit mode shows all fields as editable | @critical | Click Edit → Save + Cancel visible |
| 9 | Can enter edit mode and save | @critical | Click Edit → Save → returns to view mode |
| 10 | Cancel edit discards changes | @regression | Click Cancel → back to view mode |
| 11 | Entity detail shows Assignee + Assign to me | @smoke | "Assign to me" button visible |
| 12 | Entity detail shows Days in stage | @smoke | "Days in stage" text visible |
| 13 | Entity detail shows dates | @smoke | "today" text visible in stats row |
| 14 | Entity detail has Add a task input | @smoke | "Add a task..." placeholder visible |
| 15 | Created entity persists after reload | @critical | Reload page → search → entity still there |
| 16 | Entity data visible in table columns | @critical | Row shows entity name + "OPEN" state |

---

### Phase 12 — Field Types (`12-field-types`)

> **Purpose:** Form builder — add every field type, JSON editor, picklist management.

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | New Form dialog has entity type selector + name input | @critical | Select + text input + Create Form button |
| 2 | Can add Text field | @critical | Fill label → Add Field → field appears |
| 3 | Can add Text Area field | @critical | Same with textarea type |
| 4 | Can add Email field | @critical | Same with email type |
| 5 | Can add Phone field | @critical | Same with phone type |
| 6 | Can add Integer field | @critical | Same with integer type |
| 7 | Can add Date & Time field | @critical | Same with datetime type |
| 8 | Can add Checkbox field | @critical | Same with boolean type |
| 9 | Can add URL field | @critical | Same with url type |
| 10 | Can add Currency field | @critical | Same with currency type |
| 11 | Can add Auto Number field | @critical | Same with auto_number type |
| 12 | Form editor shows field rows | @regression | "Fields" label visible |
| 13 | Field half-width toggle works | @regression | Toggle "Full width" off → field added |
| 14 | Edit JSON button opens editor | @critical | Click → code editor/textarea visible |
| 15 | Add Picklist button clickable | @critical | Click → no crash |

---

### Phase 13 — Roles & Users Management (`13-roles-users-management`)

> **Purpose:** Role creation with full permission matrix, user management.

**Roles:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Roles list shows existing roles | @critical | Page renders with roles |
| 2 | New Role opens editor | @critical | "Create Role" or "New Role" visible |
| 3 | Editor has Display name + System name | @critical | Both labels visible |
| 4 | Editor has permission tabs | @critical | Permissions, Entity Access, Field Filteration visible |
| 5 | Editor has Save changes button | @critical | "Save changes" button visible |
| 6 | Can create role with custom name | @critical | Fill name → Save → success |
| 7 | Permissions tab shows categories | @critical | Click Permissions → content loads |
| 8 | Entity Access tab loads | @smoke | Click Entity Access → content loads |
| 9 | Forms tab in role editor loads | @smoke | Click Forms tab → content loads |
| 10 | Workflows & Transitions tab loads | @smoke | Click W&T tab → content loads |

**Users:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 11 | User list shows bootstrap admin | @critical | admin@gmail.com visible |
| 12 | User list shows bootstrap superadmin | @critical | superadmin@gmail.com visible |
| 13 | User rows show role badges | @smoke | admin/superadmin badge visible |
| 14 | Invite User has email input | @critical | Email input in dialog |
| 15 | Invite User has role selector | @critical | Role dropdown visible |
| 16 | Invite User has Send Invite button | @critical | Send/Invite button visible |
| 17 | Invite User can be cancelled | @regression | Cancel → dialog closes |
| 18 | User list has search/filter | @smoke | Search input or filter visible |

---

### Phase 14 — Comments & Dashboard Widgets (`14-comments-dashboard-widgets`)

> **Purpose:** Comment interaction and dashboard widget management.

**Comments:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Comments tab shows input | @critical | Comment input/contenteditable visible |
| 2 | Can type in comment area | @critical | Click + type → text entered |
| 3 | Activity tab shows timeline | @smoke | Click Activity → content loads |

**Dashboard:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 4 | Active Entities count visible | @critical | Widget with number |
| 5 | SLA Breaches count visible | @critical | Widget visible |
| 6 | Recent Events widget | @smoke | Widget visible |
| 7 | Pipeline by State chart | @smoke | Widget visible |
| 8 | Custom range button | @smoke | "Custom range" text |
| 9 | All time range filters (8 total) | @critical | All time, Today, This week, This month, Last 7d/30d/90d/180d |
| 10 | Today filter reloads data | @critical | Click Today → widgets still visible |
| 11 | This week filter reloads | @regression | Same for This week |
| 12 | Last 30d filter reloads | @regression | Same for Last 30d |
| 13 | Edit mode: Editing + Add widget + Cancel | @critical | Click Edit → all three visible |
| 14 | Cancel exits edit mode | @regression | Click Cancel → Edit button returns |
| 15 | Widget edit/delete icons in edit mode | @smoke | Pencil/trash SVG icons visible |
| 16 | Refresh button works | @smoke | Click Refresh → widgets reload |

---

### Phase 15 — Settings Configuration (`15-settings-configuration`)

> **Purpose:** Deep testing of individual settings modules.

| # | Test | Tag | Module | Expected Result |
|---|------|-----|--------|----------------|
| 1 | Connector form has Name input | @critical | Connectors | Name placeholder visible |
| 2 | Connector form has Base URL | @critical | Connectors | URL placeholder visible |
| 3 | Connector form has Method selector | @smoke | Connectors | GET/POST dropdown |
| 4 | Email Template editor opens | @critical | Email Templates | Click New Template → editor loads |
| 5 | Email Template search works | @smoke | Email Templates | Search input filters |
| 6 | Entity type card clickable | @critical | Entities | Click → detail opens |
| 7 | Documents tab content | @smoke | Documents | Breadcrumb visible |
| 8 | Branding settings | @smoke | Branding | Breadcrumb visible |
| 9 | Display settings | @critical | Display | Breadcrumb visible |
| 10 | Column Labels | @smoke | Column Labels | Breadcrumb visible |
| 11 | Global Filter | @smoke | Global Filter | Breadcrumb visible |
| 12 | App Labels | @smoke | App Labels | Breadcrumb visible |
| 13 | Settings search filters sidebar | @critical | Search | Type "Users" → Users button visible |
| 14 | Settings search no match | @regression | Search | Type gibberish → no crash |

---

### Phase 16 — Permissions, Connectors & Save Operations (`16-permissions-connectors-save`)

> **Purpose:** Fills every remaining gap — permission matrix, comment submit, save buttons, export.

**Roles — Entity Access Matrix:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 1 | Entity Access shows entity types | @critical | E2ETestJob visible in matrix |
| 2 | Entity Access tab loads content | @critical | Save changes button visible |
| 3 | Permissions tab shows categories | @critical | Content loads after click |
| 4 | Field Filteration shows matrix | @critical | Content loads |
| 5 | Save changes persists after editing | @critical | Toggle permission → Save → success |

**Comment Submit:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 6 | Comment input has submit button | @critical | Comment/Send/Post button visible |
| 7 | Comment area is interactive | @critical | Click → focus works |
| 8 | Typing enables submit button | @critical | Type text → button becomes clickable |
| 9 | Submitting comment adds to list | @critical | Type → Submit → comment text visible in list |

**Connector Full Form:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 10 | Name input | @critical | Placeholder visible |
| 11 | Base URL input | @critical | URL placeholder visible |
| 12 | Method selector (GET/POST) | @critical | Dropdown visible |
| 13 | Path input | @smoke | Placeholder visible |
| 14 | Auth type selector | @smoke | Dropdown visible |
| 15 | Expose as tool checkbox | @smoke | Label visible |
| 16 | Create connector button | @critical | Button visible |
| 17 | Can fill and create connector | @critical | Fill name + URL → Create → no crash |

**Settings Save Buttons:**

| # | Test | Tag | Module | Expected Result |
|---|------|-----|--------|----------------|
| 18 | Save theme button | @critical | Branding | Button visible |
| 19 | Reset to default | @smoke | Branding | Button visible |
| 20 | Save button | @critical | Display | Button visible |
| 21 | Feature flag toggles | @critical | Display | Switch elements visible |
| 22 | Save button | @critical | Column Labels | Button visible |
| 23 | Reset to defaults | @smoke | Column Labels | Button visible |
| 24 | Save button | @critical | Global Filter | Button visible |
| 25 | Save button | @critical | App Labels | Button visible |
| 26 | Reset to defaults | @smoke | App Labels | Button visible |

**Pipeline & Dashboard:**

| # | Test | Tag | Expected Result |
|---|------|-----|----------------|
| 27 | Export button has dropdown | @critical | Click Export → dropdown opens |
| 28 | Add widget opens selector | @critical | Edit mode → Add widget → content loads |
| 29 | Save in edit mode saves layout | @critical | Click Save → exits edit mode |
| 30 | Due date is a date picker | @smoke | Input type="date" |
| 31 | OPEN column shows count | @smoke | Column header visible |
| 32 | IN_REVIEW column visible | @smoke | Column visible |
| 33 | CLOSED column visible | @smoke | Column visible |
| 34 | Board shows total entity count | @smoke | Entity count text visible |

---

## Coverage Summary

| Area | Tests | Coverage Level |
|------|-------|---------------|
| Authentication | 10 | Login, OAuth buttons, forgot/reset password, invite pages |
| RBAC Permissions | 8 | Admin vs superadmin, Organizations tab, sidebar |
| Workflow / Pipeline | 20 | Board, table, calendar views, columns, search, filters, export |
| Entity CRUD | 32 | Create with all fields, edit, save, cancel, detail sections |
| Transitions | 10 | OPEN→IN_REVIEW, IN_REVIEW→CLOSED, dropdown, Move to |
| Forms & Fields | 30 | Add all field types, form builder, JSON editor, picklist |
| Dashboard | 19 | Widgets, time filters, edit mode, add/save/cancel |
| Comments | 7 | Tab navigation, input, typing, submit |
| Users & Roles | 21 | User list, invite, role editor, all permission tabs |
| Connectors | 10 | Form fields, method/auth, create |
| Email Templates | 4 | New template, search |
| Documents | 3 | Section, upload button/dropdown |
| Notifications | 2 | Bell icon, dropdown |
| Public Forms | 2 | Invalid token, branding |
| Settings Tabs | 28 | All 19 tabs load + save buttons + search |
| **Total** | **243** | |

---

## Tags Guide

| Tag | Meaning | When to run |
|-----|---------|-------------|
| `@smoke` | Basic functionality check | Every build |
| `@critical` | Core business logic | Every PR |
| `@regression` | Edge cases, cancel flows | Before release |

---

## Known Limitations

1. **Entity name pollution**: Repeated test runs create 100+ entities on the board. Entity card names can collide with button selectors. Clean the test database periodically.
2. **No Agent Mode tests**: Excluded per team decision.
3. **No drag-drop tests**: Kanban card drag between columns is unreliable in Playwright.
4. **No file upload tests**: Needs test fixture files.
5. **No OAuth flow tests**: Google/Microsoft OAuth require real credentials.
6. **Selectors rely on text**: Some tests need `data-testid` attributes for stability. Recommended: add `data-testid` to Add entity button, Save button in dialogs, and Edit button in slide-over.
