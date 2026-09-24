// Mirrors the backend's REMOTE_MCP_TOOL_NAME_PATTERN (remote_mcp/models/interface.py):
// a remote tool's id is namespaced as `remotemcp__<32-hex server id>__<tool name>` so
// the platform can route calls back to the owning server without a lookup — the same
// id lets the UI attribute a tool back to the connector that discovered it.
const REMOTE_MCP_TOOL_ID_PATTERN = /^remotemcp__([a-f0-9]{32})__.+$/;

/** Extract the owning remote MCP server's id from a namespaced tool id, or null if it isn't one. */
export function parseRemoteMcpServerId(toolId: string): string | null {
  const match = REMOTE_MCP_TOOL_ID_PATTERN.exec(toolId);
  if (!match) return null;
  const hex = match[1];
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
}
