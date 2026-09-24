# Parallel Agent Execution Plan

Suggested wave-based execution for running module agents simultaneously while minimizing dependency contention.

## Suggested waves

### Wave 1

- `identity_access_agent`: target outbound deps -> `collaboration`, `organizations`
- `collaboration_agent`: target outbound deps -> `identity_access`, `organizations`, `workflow`
- `metadata_registry_agent`: target outbound deps -> `organizations`, `projections`, `workflow`

### Wave 2

- `projections_agent`: target outbound deps -> `metadata_registry`, `organizations`, `workflow`
- `documents_agent`: target outbound deps -> `agent_ai`, `organizations`, `playbooks_runtime`, `workflow`
- `integrations_calendar_agent`: target outbound deps -> `collaboration`, `identity_access`, `organizations`, `workflow`

### Wave 3

- `transcription_agent`: target outbound deps -> `agent_ai`, `candidate_intake`, `documents`, `organizations`
- `agent_ai_agent`: target outbound deps -> `collaboration`, `documents`, `organizations`, `playbooks_runtime`, `workflow`
- `organizations_agent`: target outbound deps -> `agent_ai`, `collaboration`, `identity_access`, `metadata_registry`, `projections`

### Wave 4

- `workflow_agent`: target outbound deps -> `collaboration`, `identity_access`, `metadata_registry`, `organizations`, `projections`

### Wave 5

- `candidate_intake_agent`: target outbound deps -> `agent_ai`, `collaboration`, `documents`, `organizations`, `projections`, `workflow`
- `playbooks_runtime_agent`: target outbound deps -> `agent_ai`, `collaboration`, `documents`, `integrations_calendar`, `organizations`, `workflow`

## Cross-agent handoff protocol

1. Each agent creates/updates contracts in its own `models/interface.py` first.
2. Dependent agents consume only published contracts and avoid implicit imports.
3. Integration tests are added after both sides of a dependency edge are merged.
4. Any contract-breaking change requires coordinated updates to all impacted module agent files.

## Global blockers to watch

- Cycles among high-coupling modules (`workflow`, `projections`, `metadata_registry`, `organizations`) require staged interface-first delivery.
- Shared authz/tenancy concerns in `identity_access` and `organizations` should be finalized early to avoid rework.
- Event/side-effect modules (`collaboration`, `integrations_calendar`, `playbooks_runtime`, `agent_ai`) should standardize failure/retry semantics before broad integration.
