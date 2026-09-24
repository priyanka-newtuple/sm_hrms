# Organizations Agent Guidelines

## Agent identity

- Agent name: `organizations_agent`
- Owned module: `organizations`
- Target implementation area: `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations`
- Execution mode: independent module development with dependency-aware coordination.

## Mission

Implement and harden `organizations` in the modular backend while keeping behavior parity with current runtime source-of-truth. This agent owns code and tests inside `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations` and collaborates with dependency module agents through explicit contracts only.

## Primary references

- Module definition: `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/docs/modules/organizations.md`
- Dependency deep dive: `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/docs/dependencies/module-dependencies/organizations-dependencies.md`
- Global dependency map: `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/docs/dependencies/global-module-dependency-map.md`
- Feature dependency matrix: `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/docs/dependencies/feature-dependency-matrix.md`
- Bootstrap/wiring entrypoint: `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/main.py`

## Module context (from current definitions)

Owns organization lifecycle and tenant provisioning.

Primary domain ownership: `organizations` is responsible for organization lifecycle and tenant provisioning, and should be the only module that owns this capability end-to-end after migration.

### Current mapped sources to port from

- /Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/organizations.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/invitations.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/services/organization_service.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/services/invitation_service.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/models/organization.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/models/invitation.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/models/user.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/models/rbac.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/models/entity_type.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/schemas/organization.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/schemas/tenant_provisioning.py
- /Users/adityakumar/Desktop/ai_ats/backend/app/schemas/auth.py

### Important behavior-driving functions

- `create_organization` in `/Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/organizations.py`
- `list_organizations` in `/Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/organizations.py`
- `create_invitation` in `/Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/invitations.py`
- `list_invitations` in `/Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/invitations.py`
- `slugify` in `/Users/adityakumar/Desktop/ai_ats/backend/app/services/organization_service.py`
- `get_organization` in `/Users/adityakumar/Desktop/ai_ats/backend/app/services/organization_service.py`
- `provision_tenant` in `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`
- `get_provision_status` in `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`
- `create_invitation` in `/Users/adityakumar/Desktop/ai_ats/backend/app/services/invitation_service.py`
- `get_invitation` in `/Users/adityakumar/Desktop/ai_ats/backend/app/services/invitation_service.py`

## Required class contract (do not break)

- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations/controller.py`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations/manager.py`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations/db_models.py`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations/models/request.py`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations/models/response.py`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/organizations/models/interface.py`

## Dependency contract for parallel execution

### Current-state outbound dependencies

- agent_ai
- collaboration
- documents
- identity_access
- metadata_registry
- projections

### Current-state evidence pointers

- `organizations` -> `agent_ai` evidence: `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`
- `organizations` -> `collaboration` evidence: `/Users/adityakumar/Desktop/ai_ats/backend/app/services/invitation_service.py`
- `organizations` -> `documents` evidence: `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`
- `organizations` -> `identity_access` evidence: `/Users/adityakumar/Desktop/ai_ats/backend/app/api/routes/organizations.py`, `/Users/adityakumar/Desktop/ai_ats/backend/app/services/organization_service.py`, `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`
- `organizations` -> `metadata_registry` evidence: `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`
- `organizations` -> `projections` evidence: `/Users/adityakumar/Desktop/ai_ats/backend/app/services/tenant_provisioning_service.py`

### Target outbound dependencies (this agent calls these modules)

- agent_ai
- collaboration
- identity_access
- metadata_registry
- projections

### Target inbound dependencies (these modules call this module)

- agent_ai
- candidate_intake
- collaboration
- documents
- identity_access
- integrations_calendar
- metadata_registry
- playbooks_runtime
- projections
- transcription
- workflow

### Dependency-specific coordination rules

- Manager-to-manager/service only for cross-module calls.
- No controller-to-controller imports or calls.
- No direct DB cross-access into other module `db_models.py`.
- Shared payloads across modules must use stable class contracts under `models/interface.py`.

## Implementation guardrails

### Invariants and validation rules

- Module boundaries are strict: controller handles transport, manager handles orchestration, db_models handles persistence.
- Tenant/organization context must be preserved from request boundary to DB boundary for all module operations.
- Public API contracts should remain stable relative to current runtime behavior until cutover is approved.
- Cross-module interactions must happen through manager/service dependencies only; no controller-to-controller calls.

### Error and edge-case expectations

- Domain validation failures should map to deterministic client-safe error responses.
- Data-not-found, stale-state, and invalid-transition conditions should be explicit and non-silent.
- External-provider and downstream timeout failures should be isolated and retriable where applicable.
- Partial-write scenarios should be guarded by transaction boundaries and rollback-safe manager flows.

### Security and tenancy requirements

- Enforce role/permission checks at controller boundary before invoking manager operations.
- Enforce tenant isolation in all manager and db_models read/write filters.
- Avoid leaking sensitive fields across module boundaries; return least-privilege response payloads.
- Ensure auditability for security-relevant actions during phase-2 implementation.

### Operational requirements

- Preserve startup singleton initialization in `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/main.py`.
- Add structured logs and request IDs at controller entry/exit points.
- Add manager-level metrics (latency, error-rate, dependency-failure counters) before cutover.
- Define explicit start/stop lifecycle hooks for modules that run consumers/jobs.

## Risk profile and mitigation

### Known migration risks

- Hidden coupling in current services may surface during move to manager-to-manager dependencies.
- Model ownership overlaps can cause duplicate writes if boundaries are not stabilized first.
- Contract drift risk increases if request/response classes are introduced without compatibility tests.
- Rollout must keep `/Users/adityakumar/Desktop/ai_ats/backend/app` runtime behavior untouched until migration switch.

### Coupling notes from dependency analysis

- Coupling risk score: `10/10` (`high`).
- Primary outbound coupling pressure: `agent_ai`, `collaboration`, `identity_access`, `metadata_registry`.
- Primary inbound coupling pressure: `agent_ai`, `candidate_intake`, `collaboration`, `documents`.
- Critical concern: stabilize manager contracts and error semantics before runtime cutover.

### Circular dependency checks

- Direct mutual target dependencies: `organizations<->agent_ai`, `organizations<->collaboration`, `organizations<->identity_access`, `organizations<->metadata_registry`, `organizations<->projections`.
- Controllers must remain isolated and only register routes.
- Managers may depend on other managers/services through constructor-injected dependencies.
- `db_models.py` remains module-owned and should not be called directly by other modules.

### Recommended decoupling strategy

- Define explicit manager interfaces for each outbound dependency before logic migration.
- Move reusable cross-module payloads into `models/interface.py` contracts, not shared mutable objects.
- Add contract tests for each high-risk dependency edge and enforce strict failure behavior.
- Use event-driven boundaries for side-effect-heavy workflows to reduce synchronous coupling.

## Deliverables expected from this agent

- Implemented class-based module code in the owned paths only.
- Module-level tests covering controller, manager orchestration, and persistence boundaries.
- Compatibility proof that existing runtime API behavior remains unchanged until cutover.
- A short handoff note documenting external contracts consumed/provided.

## Done criteria

- No unresolved TODOs in owned module files.
- All module tests pass.
- Cross-module interfaces are versioned/documented in `models/interface.py`.
- Dependency assumptions match dependency docs and are validated by tests.

## Open implementation checklist reference

- [ ] Implement controller methods from mapped current routes.
- [ ] Port core business rules from mapped services into manager class methods.
- [ ] Implement DB access behavior in `db_models.py` with transactional guarantees.
- [ ] Add request/response/interface class definitions with runtime validation.
- [ ] Add module tests (controller, manager, db integration, and contract tests).
- [ ] Validate cross-module dependencies against dependency docs before enabling runtime cutover.

## Parallel handoff format (required)

When this agent needs a dependency change from another module agent, emit a handoff note with:

1. `requested_module`: target dependency module name.
2. `requested_contract`: function/class/interface signature needed.
3. `requesting_flow`: endpoint or manager flow that needs the contract.
4. `expected_error_behavior`: failure and timeout semantics.
5. `test_stub_reference`: minimal test that will fail until dependency contract is delivered.
