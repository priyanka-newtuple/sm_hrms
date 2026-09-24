/**
 * Reserved name of the built-in assistant that powers Agent Mode.
 *
 * Mirrors `AGENT_MODE_BUILTIN_NAME` in `backend/agent/services/definitions.py`.
 * The backend keys three behaviours off this name — the agent is hidden from the
 * default definitions listing, granted every tool at runtime, and cannot be
 * deactivated — so the frontend must match it exactly.
 */
export const AGENT_MODE_NAME = 'agent_mode';
