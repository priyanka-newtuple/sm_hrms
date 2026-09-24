# Agent Guidelines Index

This folder contains module-specific agent briefs for running multiple agents in parallel during modular backend implementation.

## Common references

- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/main.py`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/docs/modules`
- `/Users/adityakumar/Desktop/ai_ats/backend/modular_backend/docs/dependencies`

## Module agent files

- [`workflow_agent`](./modules/workflow-agent.md)
- [`identity_access_agent`](./modules/identity_access-agent.md)
- [`organizations_agent`](./modules/organizations-agent.md)
- [`documents_agent`](./modules/documents-agent.md)
- [`candidate_intake_agent`](./modules/candidate_intake-agent.md)
- [`collaboration_agent`](./modules/collaboration-agent.md)
- [`integrations_calendar_agent`](./modules/integrations_calendar-agent.md)
- [`playbooks_runtime_agent`](./modules/playbooks_runtime-agent.md)
- [`agent_ai_agent`](./modules/agent_ai-agent.md)
- [`transcription_agent`](./modules/transcription-agent.md)
- [`metadata_registry_agent`](./modules/metadata_registry-agent.md)
- [`projections_agent`](./modules/projections-agent.md)

## Operating constraints for all agents

- Keep edits scoped to the assigned module unless a cross-module contract update is explicitly approved.
- Preserve class-based architecture: `controller`, `manager`, `db_models`, `models/request`, `models/response`, `models/interface`.
- Respect manager-only cross-module interactions; never add controller-to-controller coupling.
- Keep `/Users/adityakumar/Desktop/ai_ats/backend/app` unchanged until migration cutover phase.
