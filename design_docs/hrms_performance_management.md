# Performance management in the HRMS application layer

Implemented 2026-09-28. This module uses the unmodified platform through public HTTP APIs. It does not add a performance controller, table, permission key or business rule to the native backend.

## Ownership

| Layer | Responsibility |
| --- | --- |
| Native platform | Entity records, configured form fields, workflow enrollment, current state, transitions and native audit |
| HRMS configuration | `performance_catalog.py`: cycle, goal, review and project-feedback entity/form/workflow definitions |
| HRMS application | `performance.py`: participants, assigned owners, validation, confidentiality, orchestration and projections |
| HRMS operation database | Request fingerprints, resumable plans, snapshots needed for recovery, human actor audit linked to operation keys |
| HRMS frontend | Cycle setup, assessment forms, stage timeline and permitted actions; integration into the unchanged core workflow table |

The application database is not a second employee/review master, but recovery plans contain copies of HR inputs. Protect and retain these records as sensitive HR data. Core audit identifies the service principal. Application audit identifies the human actor and links to the request, previous assignment and new assignment.

## Workflows

- Cycle: Draft → Pending approval → Open for goals → Review → Calibration → Published → Closed.
- Employee review: Goals draft → Goals pending → Self review → Manager review → Calibration → Ready to publish → Published → Acknowledged.
- Goals: Draft/Changes requested → Pending approval → Approved. Managers approve or return the complete goal set.
- Project feedback: Pending → Submitted.

Cycle approval requires the selected approver, an approval capability, and a different user from the author. HR Full/admin/superadmin manage cycles; admin/superadmin or the separately assigned `hrms_performance_approver` role can approve them. No existing human role assignments are changed by installation.

HR explicitly selects participants with active accounts and valid reporting managers, plus an HR calibrator. Employee/manager/calibrator names and identities are snapshotted on approval. HR can reassign an unpublished review with a required reason; previous values remain in the journal. Employees cannot assess or calibrate themselves, including when they also hold HR permissions.

Goals require measurable outcomes and weights totaling 100%. Manager approval unlocks self-review. HR starts reviews only after every participant has approved goals. Requested project feedback must be submitted before its manager review can finish. HR opens calibration only after all manager reviews finish. Calibration can return a review for manager correction, and managers can return it for self-review correction. HR publishes only when all reviews are calibrated, then closes only after every employee acknowledges.

Employee responses omit unpublished manager ratings/summary and calibrated/final ratings. Calibration notes and project feedback remain private from the employee even after publication. Partial publication does not reveal results until the parent cycle is published. Feedback reviewers see their own requested feedback, not the employee's complete review.

## Application APIs

All are relative to `/v1/api`; all require an authenticated tenant member.

| API | Purpose |
| --- | --- |
| `GET /hrms/performance` | Role/relationship-filtered cycles, reviews, goals, feedback and allowed actions |
| `GET /hrms/performance/options` | HR-only eligible participants, approvers, calibrators and users |
| `GET /hrms/performance/{review}/reviewers` | Assigned manager's feedback-reviewer options |
| `POST /hrms/performance/cycles` | Create a draft cycle |
| `POST /hrms/performance/{entity}/actions` | Validated goal/review/cycle/feedback action |
| `GET /hrms/performance/pending-actions` | Original actor's unfinished requests for safe resumption |
| `GET /hrms/workflows` | Includes performance rows in the reused core workflow table |

An action carries `action`, `data` and `idempotency_key`. Native state changes always use native transition endpoints. The browser cannot bypass product checks by directly calling native mutations through the gateway.

Mutations serialize per tenant and checkpoint every API step. Creates use a native operation marker; transitions use stable native idempotency keys. An unfinished performance plan blocks other performance writes until resumed. The Performance page shows the original actor a Resume action button. An ambiguous create without a discoverable marker fails closed for operator reconciliation; it is not blindly retried. This is a recoverable multi-call operation, not a distributed transaction. Automated reconciliation/outbox notifications remain production work.

## Local review

Open `http://localhost:5182/hrms/performance`. HR uses Create cycle; select a different approver and at least one eligible employee. The chosen approver sees Approve/Request changes. Employees and managers see only actions appropriate to their assignment and stage. These same actions are available from the Performance detail drawer in Workflows.

Run `powershell -NoProfile -File scripts/hrms-local.ps1 native-performance-test` against the seeded local stack after `native-up`. The test uses an isolated employee fixture from `native-test` and retains a named cycle, **Local performance verification**, for review. It checks native state transitions, self-approval denial, confidentiality, repeated requests, feedback and the workflow projection. It does not assess a real employee.

Verified locally: 24 application tests pass; the complete native API lifecycle and its idempotent rerun pass; the employee/onboarding/leave regression smoke test passes; the frontend production build passes. The signed-in browser shows cycle setup with eligible participants and approvers, and the reused workflow table opens review details with all stages, named owners, goals and feedback. The core boundary check confirms 1,416 original files unchanged. Existing core authentication chunk warnings remain unchanged.

## Remaining migration and production scope

The new native module is functional for new cycles. Historical legacy performance records have not been imported. Preserve legacy IDs, dates, actor history and final states during the separate migration; do not manufacture historical approvals by replaying normal transitions.

Project feedback is explicitly requested by the manager using a project reference and reviewer. Automatic discovery from legacy project allocations awaits migration of Projects/Allocations. Deadlines are recorded but do not send reminders or automatically close stages. Attachments, draft autosave, notification delivery, reporting/export, 360-degree reviews and organization-specific rating scales are not part of this implementation. The current scale is 1–5, with an explicit human-provided final calibrated rating.

Large-tenant optimization, production recovery operations, audit retention and full migration reconciliation are still required. Native field/workflow definitions are version-pinned; updating an existing published pack is an explicit configuration migration, not a silent installer overwrite.
