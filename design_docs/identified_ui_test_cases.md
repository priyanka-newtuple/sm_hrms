# Identified UI Test Cases for ATS Application

This document contains all identified test cases that can be automated using Playwright for the ATS (Applicant Tracking System) application.

## 📊 Implementation Status

**Total: 95 Test Cases | Implemented: 72 (76%) | Remaining: 23 (24%)**

- ✅ **Navigation & Layout**: 4/4 (100%)
- ⚠️ **Pipeline Board Page**: 15/29 (52%)
- ✅ **Jobs Page**: 13/13 (100%)
- ⚠️ **Candidates Page**: 13/16 (81%)
- ⚠️ **Settings Page**: 12/15 (80%)
- ✅ **Common Components**: 8/8 (100%)
- ⚠️ **Error Handling**: 7/10 (70%)

**Test Files Location**: `/frontend/e2e/`

**Status Legend**:
- ✅ = Fully implemented
- ⚠️ = Partially implemented
- ❌ = Not implemented

## Table of Contents
1. [Navigation & Layout](#navigation--layout)
2. [Pipeline Board Page](#pipeline-board-page)
3. [Jobs Page](#jobs-page)
4. [Candidates Page](#candidates-page)
5. [Settings Page](#settings-page)
6. [Common Components](#common-components)
7. [Error Handling & Edge Cases](#error-handling--edge-cases)

---

## Navigation & Layout

### TC-NAV-001: Sidebar Navigation
- **Description**: Verify sidebar navigation links work correctly
- **Steps**:
  1. Verify sidebar displays all navigation items (Pipeline, Job, Candidate, Setting)
  2. Click each navigation link
  3. Verify URL changes correctly
  4. Verify active state is highlighted
  5. Verify page content loads correctly
- **Expected**: Navigation works, active state is correct, pages load

### TC-NAV-002: Mobile Bottom Navigation
- **Description**: Verify mobile bottom navigation bar appears on small screens
- **Steps**:
  1. Resize browser to mobile viewport (< 768px)
  2. Verify bottom navigation bar appears
  3. Verify all navigation items are visible
  4. Click each navigation item
  5. Verify navigation works correctly
- **Expected**: Mobile navigation appears and functions correctly

### TC-NAV-003: Header Elements
- **Description**: Verify header elements (logo, notifications, user profile) are present
- **Steps**:
  1. Verify logo/branding is displayed
  2. Verify notification bell icon is present
  3. Verify user profile indicator is present
  4. Click notification bell (if functional)
- **Expected**: All header elements are visible

### TC-NAV-004: Responsive Layout
- **Description**: Verify layout adapts to different screen sizes
- **Steps**:
  1. Test on desktop viewport (1920x1080)
  2. Test on tablet viewport (768x1024)
  3. Test on mobile viewport (375x667)
  4. Verify sidebar hides/shows appropriately
  5. Verify content is readable and accessible
- **Expected**: Layout adapts correctly to all screen sizes

---

## Pipeline Board Page

### TC-PIPELINE-001: Page Load and Initial State
- **Description**: Verify pipeline board loads with correct initial state
- **Steps**:
  1. Navigate to Pipeline page
  2. Verify page title "Pipeline" is displayed
  3. Verify application count is displayed
  4. Verify all pipeline columns (stages) are visible
  5. Verify applications are displayed in correct columns
- **Expected**: Page loads with all columns and applications visible

### TC-PIPELINE-002: Search Functionality
- **Description**: Verify search filters applications correctly
- **Steps**:
  1. Enter search query in search box
  2. Verify applications filter in real-time
  3. Test search by candidate name
  4. Test search by job title
  5. Clear search and verify all applications reappear
- **Expected**: Search filters applications correctly by name and job title

### TC-PIPELINE-003: Job Filter Dropdown
- **Description**: Verify job filter filters applications by selected job
- **Steps**:
  1. Click job filter dropdown
  2. Verify all jobs are listed
  3. Select a specific job
  4. Verify only applications for that job are displayed
  5. Select "All Jobs" and verify all applications are shown
- **Expected**: Job filter works correctly

### TC-PIPELINE-004: Multiple Funnel Warning Banner
- **Description**: Verify warning banner appears when viewing all jobs with multiple funnels
- **Steps**:
  1. Ensure multiple jobs with different funnels exist
  2. Select "All Jobs" in filter
  3. Verify warning banner appears
  4. Verify banner message is correct
  5. Select a specific job and verify banner disappears
- **Expected**: Warning banner appears/disappears correctly

### TC-PIPELINE-005: Add Application Modal
- **Description**: Verify add application modal opens and creates application
- **Steps**:
  1. Click "Add Application" button
  2. Verify modal opens
  3. Verify form fields are present (Job Position, Candidate)
  4. Select job position from dropdown
  5. Select candidate from dropdown
  6. Click "Create Application"
  7. Verify modal closes
  8. Verify new application appears in pipeline
- **Expected**: Modal opens, form works, application is created

### TC-PIPELINE-006: Add Application Modal Validation
- **Description**: Verify form validation in add application modal
- **Steps**:
  1. Open add application modal
  2. Try to submit without selecting job
  3. Verify error message appears
  4. Select job but not candidate
  5. Try to submit
  6. Verify error message appears
  7. Fill all required fields
  8. Verify submit is enabled
- **Expected**: Validation works correctly

### TC-PIPELINE-007: Application Card Click
- **Description**: Verify clicking application card opens detail slide-over
- **Steps**:
  1. Click on an application card
  2. Verify slide-over opens from right
  3. Verify candidate name is displayed in header
  4. Verify job title is displayed as subtitle
  5. Verify application details are shown
  6. Click close button or outside slide-over
  7. Verify slide-over closes
- **Expected**: Slide-over opens and closes correctly

### TC-PIPELINE-008: Application Detail Slide-over
- **Description**: Verify application detail slide-over displays all information
- **Steps**:
  1. Open application detail slide-over
  2. Verify candidate information is displayed
  3. Verify job information is displayed
  4. Verify current state is displayed
  5. Verify available transitions are shown
  6. Verify timeline/history is displayed (if present)
- **Expected**: All application details are visible

### TC-PIPELINE-009: Column Header Click - Expand Panel
- **Description**: Verify clicking column header expands transition panel
- **Steps**:
  1. Click on a column header (e.g., "Applied")
  2. Verify panel expands below header
  3. Verify available transitions are listed
  4. Verify transition buttons are clickable
  5. Click header again
  6. Verify panel collapses
- **Expected**: Panel expands and collapses correctly

### TC-PIPELINE-010: Transition Badge Display
- **Description**: Verify transition count badge appears on columns with transitions
- **Steps**:
  1. Verify columns with available transitions show badge
  2. Verify badge displays correct count
  3. Verify columns without transitions don't show badge
  4. Hover over badge (if tooltip exists)
- **Expected**: Badges display correctly

### TC-PIPELINE-011: Execute Transition from Column Panel
- **Description**: Verify executing transition from column header panel
- **Steps**:
  1. Expand column header panel
  2. Click on a transition button
  3. Verify transition executes
  4. Verify application moves to new column
  5. Verify panel closes after transition
- **Expected**: Transition executes successfully

### TC-PIPELINE-012: Execute Transition from Application Detail
- **Description**: Verify executing transition from application detail slide-over
- **Steps**:
  1. Open application detail slide-over
  2. Click on an available transition button
  3. Verify transition executes
  4. Verify application state updates
  5. Verify application moves to correct column
  6. Verify slide-over updates or closes
- **Expected**: Transition executes from detail view

### TC-PIPELINE-013: Drag and Drop - Valid Transition
- **Description**: Verify drag and drop works for valid transitions
- **Steps**:
  1. Drag an application card
  2. Verify drag overlay appears
  3. Drag over a valid target column
  4. Verify column highlights (green/valid state)
  5. Drop the card
  6. Verify transition executes
  7. Verify application appears in new column
- **Expected**: Drag and drop works for valid transitions

### TC-PIPELINE-014: Drag and Drop - Invalid Transition
- **Description**: Verify drag and drop prevents invalid transitions
- **Steps**:
  1. Drag an application card
  2. Drag over an invalid target column
  3. Verify column shows invalid state (grayed out)
  4. Drop the card
  5. Verify error message appears
  6. Verify application remains in original column
- **Expected**: Invalid transitions are prevented

### TC-PIPELINE-015: Drag and Drop - Blocked Transition
- **Description**: Verify drag and drop shows blocked state when guards fail
- **Steps**:
  1. Drag an application card
  2. Drag over a column that requires guards
  3. Verify column shows blocked state (amber/yellow)
  4. Verify blocked reason message appears
  5. Drop the card
  6. Verify error message with reason appears
  7. Verify application remains in original column
- **Expected**: Blocked transitions show appropriate feedback

### TC-PIPELINE-016: Drag and Drop - Multiple Funnels Disabled
- **Description**: Verify drag and drop is disabled when viewing all jobs with multiple funnels
- **Steps**:
  1. Select "All Jobs" when multiple funnels exist
  2. Verify warning banner appears
  3. Try to drag an application card
  4. Verify drag is disabled or prevented
  5. Select a specific job
  6. Verify drag and drop is enabled
- **Expected**: Drag and drop disabled appropriately

### TC-PIPELINE-017: Selection Mode - Enable
- **Description**: Verify selection mode can be enabled
- **Steps**:
  1. Click "Select" button
  2. Verify selection mode is enabled
  3. Verify button text changes to "Cancel"
  4. Verify checkboxes appear on application cards
  5. Verify cards are selectable
- **Expected**: Selection mode enables correctly

### TC-PIPELINE-018: Selection Mode - Select Applications
- **Description**: Verify applications can be selected in selection mode
- **Steps**:
  1. Enable selection mode
  2. Click checkbox on multiple application cards
  3. Verify cards are highlighted/selected
  4. Verify selection count updates
  5. Click checkbox again to deselect
  6. Verify card is deselected
- **Expected**: Selection works correctly

### TC-PIPELINE-019: Selection Mode - Bulk Action Bar
- **Description**: Verify bulk action bar appears when applications are selected
- **Steps**:
  1. Enable selection mode
  2. Select multiple applications in the same state
  3. Verify bulk action bar appears at bottom
  4. Verify selected count is displayed
  5. Verify available bulk transitions are shown
  6. Deselect all applications
  7. Verify bulk action bar disappears
- **Expected**: Bulk action bar appears/disappears correctly

### TC-PIPELINE-020: Bulk Transition - Same State
- **Description**: Verify bulk transition works for applications in same state
- **Steps**:
  1. Enable selection mode
  2. Select multiple applications in the same state
  3. Click a bulk transition button
  4. Verify transition executes for all selected
  5. Verify applications move to new column
  6. Verify selection is cleared
- **Expected**: Bulk transition works correctly

### TC-PIPELINE-021: Bulk Transition - Different States
- **Description**: Verify bulk transition shows appropriate message for mixed states
- **Steps**:
  1. Enable selection mode
  2. Select applications from different states
  3. Verify bulk action bar shows message about selecting same stage
  4. Verify bulk transition buttons are not available
- **Expected**: Appropriate message shown for mixed states

### TC-PIPELINE-022: Bulk Transition - Multiple Funnels Disabled
- **Description**: Verify bulk transitions are disabled when viewing all jobs with multiple funnels
- **Steps**:
  1. Select "All Jobs" when multiple funnels exist
  2. Enable selection mode
  3. Select applications
  4. Verify bulk action bar shows message about selecting a job
  5. Verify bulk transition buttons are disabled
- **Expected**: Bulk transitions disabled appropriately

### TC-PIPELINE-023: Empty Column Display
- **Description**: Verify empty columns show appropriate message
- **Steps**:
  1. Navigate to pipeline
  2. Find a column with no applications
  3. Verify "No applications" message is displayed
  4. Drag a card over empty column
  5. Verify "Drop here" message appears
- **Expected**: Empty columns display correctly

### TC-PIPELINE-024: Application Count per Column
- **Description**: Verify application count is displayed correctly in column headers
- **Steps**:
  1. Verify each column header shows count
  2. Verify count matches number of cards in column
  3. Move an application to different column
  4. Verify counts update correctly
- **Expected**: Counts are accurate and update correctly

### TC-PIPELINE-025: Time in State Display
- **Description**: Verify time in state is displayed correctly on cards
- **Steps**:
  1. Verify each application card shows time in state
  2. Verify format is correct (e.g., "2 days", "3 hours", "Just now")
  3. Verify time updates appropriately
- **Expected**: Time in state displays correctly

### TC-PIPELINE-026: SLA Badge Display
- **Description**: Verify SLA badges appear and show correct status
- **Steps**:
  1. Find applications with SLA due dates
  2. Verify SLA badge appears
  3. Verify badge shows correct status (Overdue, hours left, days left)
  4. Verify badge color matches status (red for overdue, yellow for warning, green for OK)
- **Expected**: SLA badges display correctly

### TC-PIPELINE-027: Risk Indicator Display
- **Description**: Verify risk indicators appear on cards
- **Steps**:
  1. Find applications with HIGH risk
  2. Verify risk indicator (alert icon) appears
  3. Verify icon is red
  4. Verify applications without risk don't show indicator
- **Expected**: Risk indicators display correctly

### TC-PIPELINE-028: Loading State
- **Description**: Verify loading state is displayed while data loads
- **Steps**:
  1. Navigate to pipeline page
  2. Verify loading spinner appears initially
  3. Verify spinner disappears when data loads
  4. Verify error state if data fails to load
- **Expected**: Loading states work correctly

### TC-PIPELINE-029: Error State and Retry
- **Description**: Verify error state displays and retry works
- **Steps**:
  1. Simulate API error (if possible)
  2. Verify error message is displayed
  3. Verify "Retry" button appears
  4. Click retry button
  5. Verify data reloads
- **Expected**: Error handling works correctly

---

## Jobs Page

### TC-JOBS-001: Page Load and Initial State
- **Description**: Verify jobs page loads correctly
- **Steps**:
  1. Navigate to Jobs page
  2. Verify page title "Jobs" is displayed
  3. Verify open positions count is displayed
  4. Verify total applicants count is displayed
  5. Verify jobs grid is displayed
- **Expected**: Page loads with all information visible

### TC-JOBS-002: Jobs Grid Display
- **Description**: Verify jobs are displayed in grid format
- **Steps**:
  1. Verify jobs are displayed as cards in grid
  2. Verify each card shows job title
  3. Verify department is displayed
  4. Verify location is displayed
  5. Verify applicant count is displayed
  6. Verify days open is displayed
  7. Verify status badge is displayed
  8. Verify hiring manager is displayed
- **Expected**: All job information is visible on cards

### TC-JOBS-003: Search Jobs
- **Description**: Verify search filters jobs correctly
- **Steps**:
  1. Enter search query in search box
  2. Verify jobs filter in real-time
  3. Test search by job title
  4. Test search by department
  5. Clear search and verify all jobs reappear
- **Expected**: Search filters jobs correctly

### TC-JOBS-004: Status Filter
- **Description**: Verify status filter works correctly
- **Steps**:
  1. Click status filter dropdown
  2. Select "Open" status
  3. Verify only open jobs are displayed
  4. Select "On Hold" status
  5. Verify only on-hold jobs are displayed
  6. Select "Closed" status
  7. Verify only closed jobs are displayed
  8. Select "All Status"
  9. Verify all jobs are displayed
- **Expected**: Status filter works correctly

### TC-JOBS-005: Create Job Modal
- **Description**: Verify create job modal opens and creates job
- **Steps**:
  1. Click "Create Job" button
  2. Verify modal opens
  3. Verify all form fields are present (Title, Department, Location, Hiring Manager, Status, Pipeline)
  4. Fill in all required fields
  5. Select pipeline from dropdown
  6. Click "Create Job" button
  7. Verify modal closes
  8. Verify new job appears in grid
- **Expected**: Modal opens, form works, job is created

### TC-JOBS-006: Create Job Modal Validation
- **Description**: Verify form validation in create job modal
- **Steps**:
  1. Open create job modal
  2. Try to submit without required fields
  3. Verify error messages appear
  4. Fill in required fields
  5. Verify submit is enabled
  6. Test invalid inputs (if applicable)
- **Expected**: Validation works correctly

### TC-JOBS-007: Job Card Click
- **Description**: Verify clicking job card opens detail slide-over
- **Steps**:
  1. Click on a job card
  2. Verify slide-over opens from right
  3. Verify job title is displayed in header
  4. Verify department is displayed as subtitle
  5. Verify job details are shown
  6. Verify applicants list is shown
  7. Click close button or outside slide-over
  8. Verify slide-over closes
- **Expected**: Slide-over opens and closes correctly

### TC-JOBS-008: Job Detail Slide-over
- **Description**: Verify job detail slide-over displays all information
- **Steps**:
  1. Open job detail slide-over
  2. Verify job information is displayed
  3. Verify applicants section is displayed
  4. Verify applicant count is correct
  5. Verify "Edit job" button is present
  6. Verify applicant cards are clickable (if applicable)
- **Expected**: All job details are visible

### TC-JOBS-009: Edit Job Modal
- **Description**: Verify edit job modal opens and updates job
- **Steps**:
  1. Open job detail slide-over
  2. Click "Edit job" button
  3. Verify edit modal opens
  4. Verify form is pre-filled with current values
  5. Modify job details
  6. Click "Update Job" button
  7. Verify modal closes
  8. Verify job is updated in grid
- **Expected**: Edit modal works correctly

### TC-JOBS-010: Status Badge Display
- **Description**: Verify status badges display correctly
- **Steps**:
  1. Verify "Open" jobs show green/success badge
  2. Verify "On Hold" jobs show yellow/warning badge
  3. Verify "Closed" jobs show default/gray badge
  4. Verify badge text matches status
- **Expected**: Status badges display correctly

### TC-JOBS-011: Empty State
- **Description**: Verify empty state when no jobs match filters
- **Steps**:
  1. Apply filters that match no jobs
  2. Verify "No jobs found matching your criteria" message appears
  3. Clear filters
  4. Verify jobs reappear
- **Expected**: Empty state displays correctly

### TC-JOBS-012: Loading State
- **Description**: Verify loading state while jobs load
- **Steps**:
  1. Navigate to jobs page
  2. Verify loading spinner appears initially
  3. Verify spinner disappears when data loads
- **Expected**: Loading state works correctly

### TC-JOBS-013: Error State and Retry
- **Description**: Verify error state displays and retry works
- **Steps**:
  1. Simulate API error
  2. Verify error message is displayed
  3. Verify "Retry" button appears
  4. Click retry button
  5. Verify data reloads
- **Expected**: Error handling works correctly

---

## Candidates Page

### TC-CANDIDATES-001: Page Load and Initial State
- **Description**: Verify candidates page loads correctly
- **Steps**:
  1. Navigate to Candidates page
  2. Verify page title "Candidates" is displayed
  3. Verify candidate count is displayed
  4. Verify candidates table is displayed
- **Expected**: Page loads with all information visible

### TC-CANDIDATES-002: Candidates Table Display
- **Description**: Verify candidates are displayed in table format
- **Steps**:
  1. Verify table headers are present (Candidate, Contact, Source, Latest Application, Added, Actions)
  2. Verify each row shows candidate information
  3. Verify candidate initials/avatar is displayed
  4. Verify name is displayed
  5. Verify application count is displayed (if multiple)
  6. Verify email is displayed
  7. Verify phone is displayed (if available)
  8. Verify source is displayed
  9. Verify latest application job title and state are displayed
  10. Verify date added is displayed
- **Expected**: All candidate information is visible in table

### TC-CANDIDATES-003: Search Candidates
- **Description**: Verify search filters candidates correctly
- **Steps**:
  1. Enter search query in search box
  2. Verify candidates filter in real-time
  3. Test search by candidate name
  4. Test search by email
  5. Clear search and verify all candidates reappear
- **Expected**: Search filters candidates correctly

### TC-CANDIDATES-004: Source Filter
- **Description**: Verify source filter works correctly
- **Steps**:
  1. Click source filter dropdown
  2. Verify all unique sources are listed
  3. Select a specific source
  4. Verify only candidates from that source are displayed
  5. Select "All Sources"
  6. Verify all candidates are displayed
- **Expected**: Source filter works correctly

### TC-CANDIDATES-005: Date Filter
- **Description**: Verify date filter works correctly
- **Steps**:
  1. Click date filter dropdown
  2. Verify options are present (All Time, Today, Last 7 Days, Last 30 Days, Last 90 Days)
  3. Select "Today"
  4. Verify only candidates added today are displayed
  5. Select "Last 7 Days"
  6. Verify only candidates from last 7 days are displayed
  7. Test other date ranges
  8. Select "All Time"
  9. Verify all candidates are displayed
- **Expected**: Date filter works correctly

### TC-CANDIDATES-006: Table Column Sorting
- **Description**: Verify table columns can be sorted
- **Steps**:
  1. Click on "Candidate" column header
  2. Verify candidates sort by name (ascending)
  3. Click again to sort descending
  4. Verify sort icon changes
  5. Test sorting on "Source" column
  6. Test sorting on "Added" column
  7. Test sorting on "Application Count" column (if sortable)
- **Expected**: Column sorting works correctly

### TC-CANDIDATES-007: Sort Icon Display
- **Description**: Verify sort icons display correctly
- **Steps**:
  1. Verify unsorted columns show neutral sort icon
  2. Click column to sort ascending
  3. Verify up arrow icon appears
  4. Click again to sort descending
  5. Verify down arrow icon appears
- **Expected**: Sort icons display correctly

### TC-CANDIDATES-008: Create Candidate Modal
- **Description**: Verify create candidate modal opens and creates candidate
- **Steps**:
  1. Click "Add Candidate" button
  2. Verify modal opens
  3. Verify form fields are present (Name, Email, Phone, Source)
  4. Fill in all required fields
  5. Click "Create Candidate" button
  6. Verify modal closes
  7. Verify new candidate appears in table
- **Expected**: Modal opens, form works, candidate is created

### TC-CANDIDATES-009: Create Candidate Modal Validation
- **Description**: Verify form validation in create candidate modal
- **Steps**:
  1. Open create candidate modal
  2. Try to submit without name
  3. Verify error message appears
  4. Try to submit without email
  5. Verify error message appears
  6. Test invalid email format
  7. Verify error message appears
  8. Fill all required fields correctly
  9. Verify submit is enabled
- **Expected**: Validation works correctly

### TC-CANDIDATES-010: Edit Candidate Modal
- **Description**: Verify edit candidate modal opens and updates candidate
- **Steps**:
  1. Click "Edit candidate" button on a row
  2. Verify edit modal opens
  3. Verify form is pre-filled with current values
  4. Modify candidate details
  5. Click "Update Candidate" button
  6. Verify modal closes
  7. Verify candidate is updated in table
- **Expected**: Edit modal works correctly

### TC-CANDIDATES-011: Candidate Row Actions
- **Description**: Verify action buttons on candidate rows work
- **Steps**:
  1. Hover over a candidate row
  2. Verify action buttons appear (Edit, View, External link)
  3. Click edit button
  4. Verify edit modal opens
  5. Click other action buttons (if functional)
- **Expected**: Action buttons work correctly

### TC-CANDIDATES-012: Latest Application Badge
- **Description**: Verify latest application badge displays correctly
- **Steps**:
  1. Verify candidates with applications show latest application
  2. Verify job title is displayed
  3. Verify application state badge is displayed
  4. Verify badge color matches state (APPLIED, SCREENING, etc.)
  5. Verify candidates without applications show "No application"
- **Expected**: Latest application displays correctly

### TC-CANDIDATES-013: Application Count Display
- **Description**: Verify application count displays for candidates with multiple applications
- **Steps**:
  1. Find candidate with multiple applications
  2. Verify count is displayed (e.g., "3 applications")
  3. Verify count is accurate
- **Expected**: Application count displays correctly

### TC-CANDIDATES-014: Empty State
- **Description**: Verify empty state when no candidates match filters
- **Steps**:
  1. Apply filters that match no candidates
  2. Verify "No candidates found matching your criteria" message appears
  3. Clear filters
  4. Verify candidates reappear
- **Expected**: Empty state displays correctly

### TC-CANDIDATES-015: Loading State
- **Description**: Verify loading state while candidates load
- **Steps**:
  1. Navigate to candidates page
  2. Verify loading spinner appears initially
  3. Verify spinner disappears when data loads
- **Expected**: Loading state works correctly

### TC-CANDIDATES-016: Error State and Retry
- **Description**: Verify error state displays and retry works
- **Steps**:
  1. Simulate API error
  2. Verify error message is displayed
  3. Verify "Retry" button appears
  4. Click retry button
  5. Verify data reloads
- **Expected**: Error handling works correctly

---

## Settings Page

### TC-SETTINGS-001: Page Load and Initial State
- **Description**: Verify settings page loads correctly
- **Steps**:
  1. Navigate to Settings page
  2. Verify page title "Settings" is displayed
  3. Verify tabs are present (Funnels, Pipeline Funnel, State Machines)
  4. Verify default tab is selected
- **Expected**: Page loads with tabs visible

### TC-SETTINGS-002: Tab Navigation
- **Description**: Verify tabs can be switched
- **Steps**:
  1. Click on "Funnels" tab
  2. Verify Funnels content is displayed
  3. Click on "Pipeline Funnel" tab
  4. Verify Pipeline Funnel content is displayed
  5. Click on "State Machines" tab
  6. Verify State Machines content is displayed
  7. Verify active tab is highlighted
- **Expected**: Tab navigation works correctly

### TC-SETTINGS-003: Funnels Tab - List Display
- **Description**: Verify funnels list is displayed correctly
- **Steps**:
  1. Navigate to Funnels tab
  2. Verify funnels table is displayed
  3. Verify columns are present (Name, Status, Version, Jobs, Date, Actions)
  4. Verify funnels are listed
  5. Verify status badges are displayed
- **Expected**: Funnels list displays correctly

### TC-SETTINGS-004: Funnels Tab - Create Funnel
- **Description**: Verify create funnel button opens funnel builder
- **Steps**:
  1. Click "Create Funnel" button
  2. Verify funnel builder opens (modal or new view)
  3. Verify form fields are present
  4. Test creating a funnel (if possible)
- **Expected**: Create funnel functionality works

### TC-SETTINGS-005: Funnels Tab - Actions Menu
- **Description**: Verify funnel actions menu works
- **Steps**:
  1. Click actions menu on a funnel
  2. Verify dropdown menu appears
  3. Verify options are present (Duplicate, View JSON, Archive)
  4. Click "Duplicate"
  5. Verify duplicate functionality works (if applicable)
  6. Click "View JSON"
  7. Verify JSON is displayed (if applicable)
  8. Click "Archive"
  9. Verify archive confirmation (if applicable)
- **Expected**: Actions menu works correctly

### TC-SETTINGS-006: Pipeline Funnel Tab
- **Description**: Verify Pipeline Funnel tab content
- **Steps**:
  1. Navigate to Pipeline Funnel tab
  2. Verify content is displayed
  3. Verify form/configuration options are present
  4. Test any interactive elements
- **Expected**: Pipeline Funnel tab displays correctly

### TC-SETTINGS-007: State Machines Tab - List Display
- **Description**: Verify state machines list is displayed
- **Steps**:
  1. Navigate to State Machines tab
  2. Verify "Refresh" button is present
  3. Verify state machines are listed as cards
  4. Verify each card shows machine name, version, status
  5. Verify state and transition counts are displayed
- **Expected**: State machines list displays correctly

### TC-SETTINGS-008: State Machines Tab - Expand/Collapse
- **Description**: Verify state machine cards can be expanded/collapsed
- **Steps**:
  1. Click on a state machine card
  2. Verify card expands
  3. Verify states grid is displayed
  4. Verify transitions table is displayed
  5. Verify SLA configuration is displayed (if present)
  6. Click card again
  7. Verify card collapses
- **Expected**: Expand/collapse works correctly

### TC-SETTINGS-009: State Machines Tab - States Display
- **Description**: Verify states are displayed correctly when expanded
- **Steps**:
  1. Expand a state machine card
  2. Verify states are displayed in grid
  3. Verify initial state is marked
  4. Verify terminal states are marked
  5. Verify state icons are displayed correctly
- **Expected**: States display correctly

### TC-SETTINGS-010: State Machines Tab - Transitions Table
- **Description**: Verify transitions table displays correctly
- **Steps**:
  1. Expand a state machine card
  2. Verify transitions table is displayed
  3. Verify columns are present (Trigger, From, To, Guards)
  4. Verify transitions are listed
  5. Verify guards are displayed (if present)
- **Expected**: Transitions table displays correctly

### TC-SETTINGS-011: State Machines Tab - SLA Configuration
- **Description**: Verify SLA configuration is displayed
- **Steps**:
  1. Expand a state machine with SLA configuration
  2. Verify SLA section is displayed
  3. Verify states with SLA are listed
  4. Verify hours/days are displayed correctly
- **Expected**: SLA configuration displays correctly

### TC-SETTINGS-012: State Machines Tab - Refresh
- **Description**: Verify refresh button reloads state machines
- **Steps**:
  1. Click "Refresh" button
  2. Verify loading state appears
  3. Verify state machines reload
  4. Verify updated data is displayed
- **Expected**: Refresh works correctly

### TC-SETTINGS-013: System Information Section
- **Description**: Verify system information is displayed
- **Steps**:
  1. Navigate to State Machines tab
  2. Scroll to System Information section
  3. Verify API version is displayed
  4. Verify state machines count is displayed
  5. Verify active machines count is displayed
- **Expected**: System information displays correctly

### TC-SETTINGS-014: Loading State
- **Description**: Verify loading state while settings data loads
- **Steps**:
  1. Navigate to settings page
  2. Verify loading spinner appears initially (if applicable)
  3. Verify spinner disappears when data loads
- **Expected**: Loading state works correctly

### TC-SETTINGS-015: Error State and Retry
- **Description**: Verify error state displays and retry works
- **Steps**:
  1. Simulate API error
  2. Verify error message is displayed
  3. Verify "Retry" button appears (if applicable)
  4. Click retry button
  5. Verify data reloads
- **Expected**: Error handling works correctly

---

## Common Components

### TC-COMPONENT-001: Modal - Open and Close
- **Description**: Verify modals open and close correctly
- **Steps**:
  1. Open any modal (Add Application, Create Job, etc.)
  2. Verify modal appears with overlay
  3. Verify close button (X) is present
  4. Click close button
  5. Verify modal closes
  6. Open modal again
  7. Click outside modal (on overlay)
  8. Verify modal closes
  9. Press Escape key
  10. Verify modal closes
- **Expected**: Modals open and close via all methods

### TC-COMPONENT-002: Slide-over - Open and Close
- **Description**: Verify slide-overs open and close correctly
- **Steps**:
  1. Open any slide-over (Application Detail, Job Detail)
  2. Verify slide-over slides in from right
  3. Verify close button is present
  4. Click close button
  5. Verify slide-over closes
  6. Open slide-over again
  7. Click outside slide-over (on overlay)
  8. Verify slide-over closes
- **Expected**: Slide-overs open and close correctly

### TC-COMPONENT-003: Badge Component
- **Description**: Verify badges display correctly with different variants
- **Steps**:
  1. Verify success badges (green) display correctly
  2. Verify warning badges (yellow) display correctly
  3. Verify error badges (red) display correctly
  4. Verify default badges (gray) display correctly
  5. Verify cobalt badges (blue) display correctly
- **Expected**: All badge variants display correctly

### TC-COMPONENT-004: Dropdown/Select Component
- **Description**: Verify dropdown selects work correctly
- **Steps**:
  1. Click on any dropdown/select
  2. Verify options list appears
  3. Select an option
  4. Verify selected value is displayed
  5. Verify dropdown closes
  6. Test keyboard navigation (if applicable)
- **Expected**: Dropdowns work correctly

### TC-COMPONENT-005: Button States
- **Description**: Verify buttons show correct states
- **Steps**:
  1. Verify default button state
  2. Hover over button
  3. Verify hover state is applied
  4. Click button
  5. Verify active/pressed state (if applicable)
  6. Verify disabled state (when applicable)
- **Expected**: Button states work correctly

### TC-COMPONENT-006: Form Input Validation
- **Description**: Verify form inputs show validation states
- **Steps**:
  1. Enter invalid data in form field
  2. Verify error message appears
  3. Verify field shows error state (red border)
  4. Enter valid data
  5. Verify error message disappears
  6. Verify field shows success state (if applicable)
- **Expected**: Form validation displays correctly

### TC-COMPONENT-007: Loading Spinner
- **Description**: Verify loading spinners appear during async operations
- **Steps**:
  1. Trigger an async operation (create, update, delete)
  2. Verify loading spinner appears
  3. Verify operation completes
  4. Verify spinner disappears
- **Expected**: Loading spinners work correctly

### TC-COMPONENT-008: Empty State Messages
- **Description**: Verify empty state messages display correctly
- **Steps**:
  1. Navigate to page/section with no data
  2. Verify appropriate empty state message is displayed
  3. Verify message is helpful and clear
- **Expected**: Empty states display correctly

---

## Error Handling & Edge Cases

### TC-ERROR-001: Network Error Handling
- **Description**: Verify application handles network errors gracefully
- **Steps**:
  1. Simulate network failure
  2. Verify error message is displayed
  3. Verify retry option is available
  4. Restore network
  5. Click retry
  6. Verify data loads successfully
- **Expected**: Network errors are handled gracefully

### TC-ERROR-002: API Error Responses
- **Description**: Verify API error responses are displayed correctly
- **Steps**:
  1. Simulate 400 Bad Request error
  2. Verify appropriate error message is displayed
  3. Simulate 404 Not Found error
  4. Verify appropriate error message is displayed
  5. Simulate 409 Conflict error
  6. Verify conflict message is displayed (e.g., transition failed)
  7. Simulate 500 Server Error
  8. Verify generic error message is displayed
- **Expected**: API errors are handled appropriately

### TC-ERROR-003: Transition Failure Handling
- **Description**: Verify transition failures show detailed error messages
- **Steps**:
  1. Attempt invalid transition
  2. Verify error message appears
  3. Verify error message includes failure reason
  4. Attempt blocked transition (guards fail)
  5. Verify blocked reason is displayed
- **Expected**: Transition errors show detailed messages

### TC-ERROR-004: Form Submission Errors
- **Description**: Verify form submission errors are handled
- **Steps**:
  1. Fill form with invalid data
  2. Submit form
  3. Verify validation errors appear
  4. Fix errors
  5. Submit again
  6. Verify success message or redirect
- **Expected**: Form errors are handled correctly

### TC-ERROR-005: Concurrent Updates
- **Description**: Verify application handles concurrent updates
- **Steps**:
  1. Open application detail in two tabs
  2. Update application in first tab
  3. Attempt update in second tab
  4. Verify appropriate handling (conflict detection, refresh, etc.)
- **Expected**: Concurrent updates are handled appropriately

### TC-ERROR-006: Large Data Sets
- **Description**: Verify application handles large data sets
- **Steps**:
  1. Load page with many applications/jobs/candidates
  2. Verify pagination or virtualization works (if implemented)
  3. Verify performance is acceptable
  4. Verify all data is accessible
- **Expected**: Large data sets are handled efficiently

### TC-ERROR-007: Browser Back/Forward Navigation
- **Description**: Verify browser navigation works correctly
- **Steps**:
  1. Navigate through multiple pages
  2. Click browser back button
  3. Verify correct page is displayed
  4. Click browser forward button
  5. Verify correct page is displayed
  6. Verify state is preserved (if applicable)
- **Expected**: Browser navigation works correctly

### TC-ERROR-008: Page Refresh During Operation
- **Description**: Verify page refresh during operation
- **Steps**:
  1. Start a long-running operation (e.g., bulk transition)
  2. Refresh page
  3. Verify operation state is handled appropriately
  4. Verify no data corruption
- **Expected**: Page refresh is handled gracefully

### TC-ERROR-009: Invalid State Transitions
- **Description**: Verify invalid state transitions are prevented
- **Steps**:
  1. Attempt to transition to invalid state via drag and drop
  2. Verify transition is blocked
  3. Verify error message appears
  4. Attempt invalid transition via button
  5. Verify transition is blocked
  6. Verify error message appears
- **Expected**: Invalid transitions are prevented

### TC-ERROR-010: Missing Required Data
- **Description**: Verify application handles missing required data
- **Steps**:
  1. Navigate to page that requires data
  2. Simulate missing required data
  3. Verify appropriate fallback or error message
  4. Verify application doesn't crash
- **Expected**: Missing data is handled gracefully

---

## Test Case Summary

### Total Test Cases Identified: 95

### Breakdown by Category:
- **Navigation & Layout**: 4 test cases ✅ **All Implemented (4/4)**
- **Pipeline Board Page**: 29 test cases ⚠️ **Partially Implemented (15/29)**
- **Jobs Page**: 13 test cases ✅ **All Implemented (13/13)**
- **Candidates Page**: 16 test cases ⚠️ **Partially Implemented (13/16)**
- **Settings Page**: 15 test cases ⚠️ **Partially Implemented (12/15)**
- **Common Components**: 8 test cases ✅ **All Implemented (8/8)**
- **Error Handling & Edge Cases**: 10 test cases ⚠️ **Partially Implemented (7/10)**

### Implementation Status: **72/95 Tests Implemented (76%)**

### Missing Test Cases:

#### Pipeline Board Page (14 missing):
- TC-PIPELINE-004: Multiple Funnel Warning Banner
- TC-PIPELINE-008: Application Detail Slide-over (detail verification)
- TC-PIPELINE-010: Transition Badge Display
- TC-PIPELINE-011: Execute Transition from Column Panel
- TC-PIPELINE-012: Execute Transition from Application Detail
- TC-PIPELINE-013: Drag and Drop - Valid Transition
- TC-PIPELINE-014: Drag and Drop - Invalid Transition
- TC-PIPELINE-015: Drag and Drop - Blocked Transition
- TC-PIPELINE-016: Drag and Drop - Multiple Funnels Disabled
- TC-PIPELINE-020: Bulk Transition - Same State
- TC-PIPELINE-021: Bulk Transition - Different States
- TC-PIPELINE-022: Bulk Transition - Multiple Funnels Disabled
- TC-PIPELINE-025: Time in State Display
- TC-PIPELINE-026: SLA Badge Display
- TC-PIPELINE-027: Risk Indicator Display

#### Candidates Page (3 missing):
- TC-CANDIDATES-007: Sort Icon Display
- TC-CANDIDATES-013: Application Count Display

#### Settings Page (3 missing):
- TC-SETTINGS-005: Funnels Tab - Actions Menu
- TC-SETTINGS-006: Pipeline Funnel Tab
- TC-SETTINGS-011: State Machines Tab - SLA Configuration
- TC-SETTINGS-015: Error State and Retry

#### Error Handling (3 missing):
- TC-ERROR-005: Concurrent Updates
- TC-ERROR-006: Large Data Sets
- TC-ERROR-008: Page Refresh During Operation

### Priority Levels (Suggested):
- **High Priority**: Core functionality (CRUD operations, transitions, navigation)
- **Medium Priority**: Filtering, searching, sorting, bulk operations
- **Low Priority**: UI polish, edge cases, error scenarios

### Automation Notes:
- Most test cases are suitable for Playwright automation
- Drag and drop operations can be automated using Playwright's drag and drop API
- Modal and slide-over interactions are straightforward to automate
- Form validation can be tested by submitting invalid data
- Error scenarios can be simulated by mocking API responses
- Loading states can be verified by checking for spinner elements

### Recommended Test Execution Order:
1. Navigation and layout tests (establish baseline)
2. CRUD operations (Create, Read, Update, Delete)
3. Core workflows (transitions, drag and drop)
4. Filtering and searching
5. Bulk operations
6. Error handling
7. Edge cases

---

## Notes for Test Implementation

1. **Test Data Setup**: Ensure test data is available or can be created via API/seed scripts
2. **API Mocking**: Consider using Playwright's route interception for error scenarios
3. **Wait Strategies**: Use appropriate wait strategies for async operations (networkidle, element visibility)
4. **Screenshots**: Capture screenshots on failures for debugging
5. **Test Isolation**: Ensure tests are independent and can run in any order
6. **Cleanup**: Clean up test data after test execution
7. **Parallel Execution**: Tests can be run in parallel for faster execution
8. **CI/CD Integration**: Tests should be integrated into CI/CD pipeline

---

---

## Implementation Status

### ✅ Implemented Test Files

All test files have been created in `/frontend/e2e/`:

1. **navigation.spec.ts** - 4 tests (100% complete)
2. **pipeline.spec.ts** - 15 tests (52% complete, 14 tests remaining)
3. **jobs.spec.ts** - 13 tests (100% complete)
4. **candidates.spec.ts** - 13 tests (81% complete, 3 tests remaining)
5. **settings.spec.ts** - 12 tests (80% complete, 3 tests remaining)
6. **components.spec.ts** - 8 tests (100% complete)
7. **error-handling.spec.ts** - 7 tests (70% complete, 3 tests remaining)

### 📁 Supporting Files Created

- `playwright.config.ts` - Playwright configuration
- `helpers/test-helpers.ts` - Reusable test helper functions
- `fixtures/test-data.ts` - Test data constants
- `README.md` - Test documentation
- `TEST_IMPLEMENTATION_SUMMARY.md` - Implementation summary

### 🚀 How to Run Tests

1. **Install Playwright browsers:**
   ```bash
   cd frontend
   npx playwright install
   ```

2. **Ensure backend is running** on `http://localhost:8000`

3. **Run all tests:**
   ```bash
   npm run test:e2e
   ```

4. **Run tests in UI mode (interactive):**
   ```bash
   npm run test:e2e:ui
   ```

5. **Run tests with visible browser:**
   ```bash
   npm run test:e2e:headed
   ```

6. **View test report:**
   ```bash
   npm run test:e2e:report
   ```

### 📝 Notes

- The Playwright config automatically starts the frontend dev server
- Tests are designed to be independent and can run in parallel
- Screenshots are captured on test failures
- Some tests may require specific test data in the database

---

*Document generated based on UI exploration and codebase analysis*
*Last Updated: December 31, 2024*
*Implementation Status: 72/95 tests implemented (76%)*

