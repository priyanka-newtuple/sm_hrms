# Comments Module

Self-contained module for all comment functionality on the Newtuple platform. Comments are attached to entities (e.g. job applications, candidates) and optionally scoped to a specific workflow and state. The module handles authorship, visibility/access control, @mentions with notifications, and full edit history.

---

## Module Structure

```
comments/
├── controller.py       REST endpoints (CommentsRestController)
├── manager.py          Business logic (CommentsServiceManager)
├── db_models.py        ORM model + DB persistence service (Comment, CommentModelService)
└── models/
    ├── request.py      Inbound Pydantic schemas (CommentCreateRequest, CommentUpdateRequest)
    ├── response.py     Outbound Pydantic schemas (CommentResponse, CommentListResponse)
    └── interface.py    Shared types (CommentThreadKey, normalize_mentions)
```

---

## API Endpoints

All routes are mounted under `/v1/api` and require a valid JWT (Bearer token). The actor's `user_id`, `organization_id`, and `roles` are read from the token and used for authorization.

Responses use standard HTTP status codes. Errors are returned as JSON with a `detail` field (FastAPI default).

### 1. Create a Comment

```
POST /v1/api/entities/{entity_id}/comments
```

Posts a new comment on an entity. The author identity is resolved from the JWT — the caller cannot supply their own `author_id`. Mentions embedded in the text using `@[Full Name](user_id)` syntax are validated against active users in the same organization and stored as structured objects.

**Path parameters**

| Parameter   | Type   | Description                      |
|-------------|--------|----------------------------------|
| `entity_id` | string | UUID of the entity to comment on |

**Request body** — `CommentCreateRequest`

| Field              | Type            | Required | Default | Description |
|--------------------|-----------------|----------|---------|-------------|
| `text`             | string          | yes      | —       | Comment body. Cannot be blank. Supports `@[Name](user_id)` mention syntax. |
| `visibility`       | string (enum)   | no       | `"all"` | Who can see this comment. One of `all`, `internal`, `role_restricted`. |
| `visible_to_roles` | list of strings | no       | `null`  | Required when `visibility` is `role_restricted`. |
| `workflow_id`      | string          | no       | `null`  | UUID of the workflow to scope this comment to. The backend resolves the current state name automatically from the entity's enrollment. |

**Example request**

```json
{
  "text": "Please review the offer letter. cc @[Jane Smith](user-abc-123)",
  "visibility": "internal",
  "workflow_id": "wf-001"
}
```

**Response** `201 Created` — `CommentResponse`

**Error responses**

| Status | Reason |
|--------|--------|
| `400`  | `text` is blank, invalid `visibility` value, or `role_restricted` without `visible_to_roles` |
| `401`  | Missing or invalid JWT |
| `403`  | Actor is from a different organization |
| `404`  | Entity not found in the database |

---

### 2. List Comments for an Entity

```
GET /v1/api/entities/{entity_id}/comments
```

Returns all visible, non-archived comments on an entity, regardless of which workflow version the entity currently points to. Comments the actor is not permitted to see (based on `visibility` and their roles) are silently omitted from the response.

**Visibility filtering rules:**

| Comment visibility | Who can see it |
|--------------------|----------------|
| `all`              | Everyone |
| `internal`         | Everyone (role restriction not currently enforced) |
| `role_restricted`  | Users whose roles intersect with `visible_to_roles` |

**Path parameters**

| Parameter   | Type   | Description          |
|-------------|--------|----------------------|
| `entity_id` | string | UUID of the entity   |

**Query parameters**

| Parameter          | Type    | Required | Default | Description |
|--------------------|---------|----------|---------|-------------|
| `state_name`       | string  | no       | —       | Filter comments to a specific state name (e.g. `APPLIED`) |
| `include_archived` | boolean | no       | `false` | When `true`, includes soft-deleted comments |

**Response** `200 OK` — `CommentListResponse`

**Error responses**

| Status | Reason |
|--------|--------|
| `401`  | Missing or invalid JWT |
| `403`  | Actor is from a different organization |

---

### 3. Edit a Comment

```
PATCH /v1/api/comments/{comment_id}
```

Updates the text of an existing comment. The old text is moved to `edit_history` before being replaced. Mentions are re-parsed and re-validated; existing mention notifications are replaced.

**Who can edit:**
- The original author
- Users with roles `admin`, `owner`, or `superadmin`

**Path parameters**

| Parameter    | Type   | Description          |
|--------------|--------|----------------------|
| `comment_id` | string | UUID of the comment  |

**Request body** — `CommentUpdateRequest`

| Field  | Type   | Required | Description |
|--------|--------|----------|-------------|
| `text` | string | yes      | New comment text. Cannot be blank. |

**Example request**

```json
{
  "text": "Updated: please also check the background verification docs."
}
```

**Response** `200 OK` — `CommentResponse` with updated `text`, `is_edited: true`, `edited_at` timestamp, and the previous version appended to `edit_history`.

**Error responses**

| Status | Reason |
|--------|--------|
| `400`  | `text` is blank, or the comment has already been archived |
| `401`  | Missing or invalid JWT |
| `403`  | Actor is not the author and does not have an admin role |
| `404`  | Comment not found in this organization |

---

### 4. Delete (Archive) a Comment

```
DELETE /v1/api/comments/{comment_id}
```

Soft-deletes a comment by setting `archived_at` and `archived_by`. The record is retained in the database and can be retrieved with `include_archived=true`. Mention notifications sourced from this comment are also deleted.

**Who can delete:** Only the original author. Admins cannot delete other users' comments (by design — use archiving for moderation if needed).

**Path parameters**

| Parameter    | Type   | Description          |
|--------------|--------|----------------------|
| `comment_id` | string | UUID of the comment  |

**Response** `200 OK`

```json
{ "message": "Comment archived successfully" }
```

**Error responses**

| Status | Reason |
|--------|--------|
| `400`  | Comment is already archived |
| `401`  | Missing or invalid JWT |
| `403`  | Actor is not the comment author |
| `404`  | Comment not found in this organization |

---

### 5. Module Status

```
GET /v1/api/comments/status
```

Health/readiness check for the comments module.

**Response** `200 OK`

```json
{
  "module": "comments",
  "status": "ready",
  "started": true
}
```

---

## Request Schemas

### `CommentCreateRequest`

```
CommentCreateRequest
├── text               string        required   Comment body text
├── visibility         string        optional   "all" | "internal" | "role_restricted"  (default: "all")
├── visible_to_roles   list[string]  optional   Required if visibility == "role_restricted"
└── workflow_id        string        optional   Scope comment to a workflow (state name resolved automatically)
```

### `CommentUpdateRequest`

```
CommentUpdateRequest
└── text               string        required   Replacement comment text
```

---

## Response Schemas

### `CommentResponse`

Returned by create, edit, and as list items.

```
CommentResponse
├── id                 string        UUID of the comment
├── organization_id    string        UUID of the owning organization
├── entity_id          string        UUID of the entity this comment belongs to
├── entity_type        string        Type identifier of the entity (e.g. "application")
├── workflow_id        string | null UUID of the workflow (if scoped)
├── state_id           string | null Opaque UUID of the workflow enrollment row (set by server)
├── state_name         string | null Name of the workflow state at time of posting
├── text               string        Current comment body
├── mentions           list[dict]    Validated @mention objects (see Mention object below)
├── author_id          string | null UUID of the author (null if anonymous/system)
├── author_name        string        Display name of the author at time of posting
├── author_role        string | null Role of the author at time of posting
├── author_avatar_url  string | null Avatar URL of the author at time of posting
├── visibility         string        "all" | "internal" | "role_restricted"
├── visible_to_roles   list[string] | null  Roles allowed to see the comment (if role_restricted)
├── is_edited          boolean       Whether the comment has been edited at least once
├── edited_at          string | null ISO 8601 timestamp of the last edit
├── edit_history       list[dict]    Full edit log (see EditHistoryEntry below)
├── archived_at        string | null ISO 8601 timestamp of deletion (null = active)
├── archived_by        string | null UUID of user who archived the comment
└── created_at         string        ISO 8601 timestamp when the comment was created
```

**Mention object** (inside `mentions` array):

```json
{
  "user_id": "user-abc-123",
  "full_name": "Jane Smith",
  "position": 42
}
```

`position` is the character offset of the `@[...]` token in the original text.

**EditHistoryEntry object** (inside `edit_history` array):

```json
{
  "previous_text": "The old comment body",
  "edited_at": "2026-05-16T10:30:00+00:00",
  "edited_by_id": "user-abc-123",
  "edited_by_name": "Jane Smith"
}
```

### `CommentListResponse`

```
CommentListResponse
├── comments    list[CommentResponse]   Visible, filtered comments
└── total       integer                 Count of comments in this response
```

---

## Database Schema

**Table:** `comments`

| Column             | Type           | Nullable | Default   | Description |
|--------------------|----------------|----------|-----------|-------------|
| `id`               | `VARCHAR(36)`  | NOT NULL | `uuid4()` | Primary key |
| `organization_id`  | `VARCHAR(36)`  | NOT NULL | —         | Tenant scoping |
| `entity_id`        | `VARCHAR(36)`  | NOT NULL | —         | The entity this comment is attached to |
| `entity_type`      | `VARCHAR(128)` | NOT NULL | —         | Entity type identifier resolved at write time |
| `workflow_id`      | `VARCHAR(36)`  | NULL     | —         | Optional workflow scope |
| `state_id`         | `VARCHAR(36)`  | NULL     | —         | Enrollment row UUID from `entity_state` — set by server |
| `state_name`       | `VARCHAR(128)` | NULL     | —         | State name snapshot at write time |
| `text`             | `TEXT`         | NOT NULL | —         | Comment body |
| `mentions`         | `JSONB`        | NOT NULL | `[]`      | Array of `{user_id, full_name, position}` objects |
| `edit_history`     | `JSONB`        | NOT NULL | `[]`      | Array of `{previous_text, edited_at, edited_by_id, edited_by_name}` objects |
| `author_id`        | `VARCHAR(36)`  | NULL     | —         | UUID of the author (nullable for system-generated comments) |
| `author_name`      | `VARCHAR(256)` | NOT NULL | —         | Author display name snapshot at write time |
| `author_role`      | `VARCHAR(64)`  | NULL     | —         | Author role snapshot at write time |
| `author_avatar_url`| `VARCHAR(2048)`| NULL     | —         | Author avatar URL snapshot at write time |
| `visibility`       | `VARCHAR(32)`  | NOT NULL | `'all'`   | `all` / `internal` / `role_restricted` |
| `visible_to_roles` | `JSONB`        | NULL     | —         | List of role names (only when `visibility = role_restricted`) |
| `is_edited`        | `BOOLEAN`      | NOT NULL | `false`   | Set to `true` after the first edit |
| `edited_at`        | `TIMESTAMPTZ`  | NULL     | —         | Timestamp of the most recent edit |
| `archived_at`      | `TIMESTAMPTZ`  | NULL     | —         | Soft-delete timestamp; `null` means the comment is active |
| `archived_by`      | `VARCHAR(36)`  | NULL     | —         | UUID of the user who archived it |
| `created_at`       | `TIMESTAMPTZ`  | NOT NULL | `now()`   | Insertion timestamp, set by the database |

### Indexes

| Index name                           | Columns                                | Purpose |
|--------------------------------------|----------------------------------------|---------|
| `ix_comments_entity_org`             | `(entity_id, organization_id)`         | Primary query pattern: all comments for an entity within an org |
| `ix_comments_entity_workflow_state`  | `(entity_id, workflow_id, state_id)`   | Filtered queries scoped to a workflow/state |
| `ix_comments_active`                 | `(entity_id, archived_at)`             | Efficiently exclude archived comments |
| `ix_comments_author`                 | `(author_id)`                          | Look up all comments by a specific user |
| `ix_comments_created`                | `(created_at)`                         | Time-based ordering and range queries |

### Soft-delete pattern

Comments are never hard-deleted from the database. A `DELETE` API call sets `archived_at` (and `archived_by`) on the row. The list endpoint filters these out by default (`archived_at IS NULL`). Pass `include_archived=true` to retrieve them. This preserves audit history and allows future moderation features.

### Mention syntax

Mentions are written inline in the `text` field using the format:

```
@[Full Name](user_id)
```

Example: `"Great candidate! cc @[Jane Smith](user-abc-123)"`

At write time the manager:
1. Parses all `@[Name](id)` tokens from the text with their character positions.
2. Validates each mentioned user exists, is active, and belongs to the same organization.
3. Skips any self-mention (author mentioning themselves).
4. Stores only the validated mentions as structured objects in the `mentions` JSONB column.
5. Fires a `create_mention_notification` for each valid mention via the notifications module.

On edit, the previous mention notifications for the comment are deleted and re-created based on the updated mention list.

---

## Visibility Model

| Value             | Who sees the comment |
|-------------------|----------------------|
| `all`             | Any authenticated user with access to the entity |
| `internal`        | Any authenticated user with access to the entity (role restriction not currently enforced) |
| `role_restricted` | Users whose role list intersects `visible_to_roles` |

Visibility is enforced in `CommentsServiceManager.list_comments` — comments the actor cannot see are silently excluded from the response, not returned as errors.

---

## Authorization Summary

| Operation | Who is allowed |
|-----------|----------------|
| Create    | Any authenticated user in the same organization |
| List      | Any authenticated user in the same organization |
| Edit      | Comment author, or users with role `admin` / `owner` / `superadmin` |
| Delete    | Comment author only |
