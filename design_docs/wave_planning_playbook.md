# Wave Planning Playbook

Generalized process for grooming a batch of feature requests and bugs into parallel development waves. This playbook is used by Claude Code agents when the user requests development planning, sprint grooming, or wave-based task organization.

---

## When to Use This Playbook

Use this when:
- The user provides a list of feature requests, bugs, or requirements to plan
- The user asks for "grooming", "sprint planning", "wave planning", or "swarm development"
- Multiple tickets need to be organized for parallel agent execution

---

## Phase 1: Requirement Intake

**Goal:** Create initial ticket stubs from raw requirements.

1. Collect all feature requests, bugs, and requirements from the user
2. Assign ticket IDs (e.g., `SWARM-01`, `SPRINT-01`, or user's preferred convention)
3. For each ticket, write:
   - **Description** — 2-3 sentences explaining the feature/bug
   - **User Scenarios** — 1-3 concrete examples of how the feature will be used (use stakeholder names if provided)
   - **Initial Acceptance Criteria** — checkbox list of what "done" looks like
4. Present the ticket stubs to the user for review before proceeding

---

## Phase 2: Codebase Analysis

**Goal:** Understand what exists and what needs to change for each ticket.

For each ticket, explore the codebase to identify:

1. **Existing modules to reuse** — services, models, components, routes, utilities that already do part of what's needed. Format as a table:
   ```
   | Module | Location | Reuse |
   |--------|----------|-------|
   | Entity creation | entity_service.create_entity() | Core creation logic |
   ```

2. **Files that will need modification** — existing files that must change. Tag each as MODIFIED.

3. **Files that will need creation** — new services, routes, components, migrations. Tag each as NEW.

4. **Database migrations needed** — determine if the ticket requires:
   - **DDL migration** — new tables, columns, indexes
   - **Data migration** — seeding default data, updating existing records
   - **None** — pure code change, or data stored in JSON fields

5. **New dependencies** — any new pip/npm packages required

---

## Phase 3: Grooming Interview

**Goal:** Resolve ambiguity by asking the user targeted questions.

1. For each ticket, generate 2-4 open questions covering:
   - **Scope decisions** — what's in vs. out for this iteration
   - **Design choices** — when multiple valid approaches exist
   - **Behavior specifics** — edge cases, defaults, limits
   - **Integration points** — how this ticket interacts with existing features

2. Present all questions grouped by ticket, with response placeholders:
   ```
   **Q1.1:** Should X do Y or Z?
   **Answer:**
   ```

3. After receiving answers, consolidate into a **Grooming Decisions** section per ticket — short bullet points, not Q&A format.

4. Update acceptance criteria based on the answers.

---

## Phase 4: Targeted Audit (if applicable)

**Goal:** Surface hidden issues that affect the tickets.

Run audits when tickets touch sensitive areas:

- **Multi-tenancy** — search for entity queries missing `organization_id` filters. Pattern: `db.query(Entity).filter(Entity.entity_id ==` without `.filter(Entity.organization_id ==`
- **Auth/RBAC** — check that new endpoints have proper role guards
- **Data access** — verify new queries are scoped to the user's organization
- **Cross-service consistency** — check that service function signatures pass org_id through the call chain

For each finding, document:
- File, function, line number
- Severity (CRITICAL / HIGH / MEDIUM)
- Whether the fix context (e.g., org_id) is already available in scope
- Attack scenario if exploited

Present audit results in the relevant ticket(s) and let the user decide scope.

---

## Phase 5: System Design

**Goal:** High-level architecture for each ticket — enough for an agent to build from.

For each ticket, create:

1. **Flow diagram** (ASCII art) showing the data flow:
   ```
   User action → API endpoint → Service → Database
                                        → External API
   ```

2. **Backend changes** — tagged as NEW or MODIFIED with file names:
   ```
   - NEW: some_service.py — description
   - MODIFIED: existing_service.py — what changes
   ```

3. **Frontend changes** — same format:
   ```
   - NEW: SomeComponent.tsx — description
   - MODIFIED: ExistingPage.tsx — what changes
   ```

4. **Migration details** (if applicable):
   - Migration number (check current Alembic head via `ls backend/alembic/versions/`)
   - Type: DDL or Data
   - Brief description

Keep designs high-level — describe WHAT changes, not HOW to implement each line.

---

## Phase 6: Dependency Analysis & Wave Assignment

**Goal:** Maximize parallelism by identifying which tickets conflict.

### Step 1: Build the File Conflict Matrix

For each ticket, list every file it will modify (not create — new files don't conflict). Then find overlaps:

```
| Shared File | Tickets | Conflict Type |
|-------------|---------|---------------|
| some_service.py | TICKET-01, TICKET-03 | Both modify same functions |
```

### Step 2: Build the Dependency Graph

Identify blocking relationships:
- **File conflict** — tickets that modify the same file cannot run in the same wave
- **Logical dependency** — ticket B needs ticket A's changes to work correctly
- **Migration ordering** — data migrations may depend on DDL migrations

```
TICKET-01 ──blocks──→ TICKET-03 (both modify service_x.py)
TICKET-02 ──blocks──→ TICKET-05 (logical: feature B needs feature A)
```

### Step 3: Assign Waves

Group tickets into waves following these rules:

1. **P1 (Wave 1):** All tickets with NO file conflicts between them. Maximize this group.
2. **P2 (Wave 2):** Tickets blocked by P1 tickets. Can run in parallel with each other if they don't conflict.
3. **P3 (Wave 3):** Tickets blocked by P2 tickets.
4. Continue as needed.

Priority within a wave:
- Security fixes first (bugs that affect data isolation, auth)
- Bugs before features
- Smaller tickets before larger ones (faster unblocking)

### Step 4: Assign Migration Numbers

- Check current Alembic head: `ls backend/alembic/versions/ | sort | tail -1`
- Assign sequential numbers starting from head + 1
- Assign by wave order (all P1 migrations first, then P2, then P3)
- **CRITICAL — Migration chain rule:** Even though tickets in the same wave run on separate branches, Alembic requires a **strictly linear chain**. Migrations within the same wave MUST chain sequentially:
  ```
  head (041) → 042 (ticket A) → 043 (ticket B) → 044 (ticket C)
  ```
  NOT:
  ```
  head (041) → 042 (ticket A)
  head (041) → 043 (ticket B)   ← WRONG: creates multiple heads!
  ```
  **Every migration's `down_revision` must point to the previous migration number, not to the pre-wave head.** The Migration Number Registry defines the chain order — agents MUST set their `down_revision` to `N-1`, not to the original head.
- Create a **Migration Number Registry** table:
  ```
  | Migration | Ticket | Type | down_revision | Description |
  |-----------|--------|------|---------------|-------------|
  | 042 | TICKET-A | DDL | 041 | Create some_table |
  | 043 | TICKET-B | Data | 042 | Seed data for existing tenants |
  | 044 | TICKET-C | DDL | 043 | Add new column |
  ```
- **Merge-time verification:** After merging all branches from a wave, run `alembic heads` to confirm there is exactly ONE head. If multiple heads appear, fix the `down_revision` chain before proceeding.
- **Idempotency guards required:** ALL DDL migrations that create tables MUST include a `table_exists()` guard to handle cases where the table was created outside of Alembic (e.g., by SQLAlchemy `create_all()` during development). Pattern:
  ```python
  from sqlalchemy import inspect

  def _table_exists(name: str) -> bool:
      bind = op.get_bind()
      return name in inspect(bind).get_table_names()

  def upgrade() -> None:
      if _table_exists("my_table"):
          return
      op.create_table("my_table", ...)
  ```
  This is an established pattern in this codebase — see migrations 037, 038, 039, 040 for examples. Agents MUST follow this pattern.

---

## Phase 7: Document Assembly

**Goal:** Produce the final grooming document organized for agent execution.

### Document Structure

```markdown
# [Session Name] — [Date]

[Brief intro]

**Current Alembic head:** `NNN`

---

## Dependency Graph
[ASCII dependency graph]

## File Conflict Matrix
[Table of shared files and conflicting tickets]

## Priority Waves
[Tables with: Done checkbox, Ticket, Agent name, Branch, Blocked By, Status]

---

## TICKET-XX: [Title]

| | |
|---|---|
| **Wave** | **P1/P2/P3** |
| **Type** | Feature / Bug / Performance |
| **Reporter** | [Name] |
| **Migration** | `NNN_description` or None |
| **Branch** | `feat/ticket-xx-short-name` |

### Description
### Grooming Decisions
### Acceptance Criteria
### System Design
### Existing Modules to Reuse
### Agent Feedback

> _Agent: fill in after picking up the ticket._

**Started:** _date_
**Completed:** _date_
**Notes:**
```

[Repeat per ticket, ordered by wave then priority]

```markdown
## Migration Number Registry
[Table of all reserved migration numbers]
```

### Key Principles

- **Tickets ordered by wave** — P1 tickets first in the document, then P2, then P3
- **Self-contained tickets** — each ticket has everything an agent needs to start work
- **Agent Feedback section** — every ticket must have a feedback area for the executing agent
- **No orphan Q&A** — grooming answers are consolidated into "Grooming Decisions" bullets, not left as separate Q&A sections
- **Branch naming convention:** `fix/` for bugs, `feat/` for features, `perf/` for performance

---

## Checklist Before Presenting to User

- [ ] Every ticket has: description, grooming decisions, acceptance criteria, system design, agent feedback section
- [ ] Dependency graph accounts for all file-level conflicts
- [ ] Wave assignment maximizes parallelism (no unnecessary sequencing)
- [ ] Migration numbers are sequential and non-overlapping
- [ ] Security/multi-tenancy concerns are flagged if relevant
- [ ] Each ticket specifies which files are NEW vs MODIFIED
- [ ] Branch names assigned per ticket
