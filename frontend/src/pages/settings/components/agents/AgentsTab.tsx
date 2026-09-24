import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Bot,
  Plus,
  Loader2,
  Wrench,
  Lock,
  Sparkles,
  Trash2,
  Edit,
  Check,
  X,
  AlertCircle,
  Play,
  PanelRightClose,
  PanelRightOpen,
  RefreshCcw,
  MessageSquare,
  ChevronRight,
  Search,
} from 'lucide-react';

import { agent, aiFeatures, mcp, getApiErrorMessage } from '../../../../core/services/api';
import type {
  AgentDefinitionListItem,
  AgentDefinition,
  AgentToolInfo,
  ProviderModels,
  PendingAction,
  ToolCallInfo,
  AgentMessage,
} from '../../../../core/types';
import Badge from '../../../../core/components/Badge';
import AlertBanner from '../../../../core/components/AlertBanner';
import { AGENT_MODE_NAME } from '../../../../core/constants/agents';
import { Button } from '@/components/ui/button';
import {
  Combobox,
  ComboboxCollection,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxInput,
  ComboboxItem,
  ComboboxLabel,
  ComboboxList,
} from '@/components/ui/combobox';
import { useOrgSelector } from '../../../../core/contexts/OrgSelectorContext';

interface ModelOption {
  value: string;
  label: string;
  providerName: string;
}

interface ModelOptionGroup {
  value: string;
  items: ModelOption[];
}

interface AgentEditorProps {
  agent: AgentDefinition | null;
  tools: AgentToolInfo[];
  availableModels: ProviderModels[];
  modelsLoading: boolean;
  onSave: (data: Partial<AgentDefinition>) => Promise<void>;
  onClose: () => void;
  isNew?: boolean;
}

function AgentEditor({ agent: agentData, tools, availableModels, modelsLoading, onSave, onClose, isNew }: AgentEditorProps) {
  // agent_mode (Flowtuple AI Agent) is granted every tool at runtime by the
  // backend, which short-circuits allowed_tools entirely. Its tool section is
  // therefore rendered read-only: showing an editable list would present a
  // field whose saved value is ignored. Every other field on this agent is
  // editable like any other seeded system agent.
  const hasAllToolsGrant = agentData?.name === AGENT_MODE_NAME;
  // Derived from the grant alone, never from `allowed_tools === null` — the
  // stored value is irrelevant for this agent, and keying off it would render
  // "0 tools enabled" for an agent that actually has all of them.
  const allToolsEnabled = hasAllToolsGrant;
  const [formData, setFormData] = useState({
    name: agentData?.name || '',
    display_name: agentData?.display_name || '',
    description: agentData?.description || '',
    system_prompt: agentData?.system_prompt || '',
    allowed_tools: agentData?.allowed_tools ?? [],
    constraints: {
      // Spread first so keys this form does not edit (e.g. temperature) survive
      // the round-trip; the backend replaces `constraints` wholesale on update.
      ...agentData?.constraints,
      max_iterations: agentData?.constraints?.max_iterations ?? 10,
      require_approval: agentData?.constraints?.require_approval ?? [],
    },
    suggestions: agentData?.suggestions || [],
    model_override: agentData?.model_override || null,
    is_active: agentData?.is_active ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [newSuggestion, setNewSuggestion] = useState({ label: '', prompt: '' });
  const [toolQuery, setToolQuery] = useState('');

  // Filter only which tool rows are shown; selection state (allowed_tools) is untouched.
  const visibleTools = useMemo(() => {
    const q = toolQuery.trim().toLowerCase();
    if (!q) return tools;
    return tools.filter((t) => (t.display_name || t.name).toLowerCase().includes(q));
  }, [tools, toolQuery]);

  const modelGroups = useMemo<ModelOptionGroup[]>(
    () => availableModels
      .filter(provider => provider.models.length > 0)
      .map(provider => ({
        value: provider.provider_name,
        items: provider.models.map(model => ({
          value: model.id,
          label: model.name,
          providerName: provider.provider_name,
        })),
      })),
    [availableModels],
  );

  const selectedModel = useMemo(
    () => modelGroups
      .flatMap(group => group.items)
      .find(model => model.value === formData.model_override)
      ?? (formData.model_override
        ? {
            value: formData.model_override,
            label: formData.model_override,
            providerName: 'Currently selected',
          }
        : null),
    [formData.model_override, modelGroups],
  );

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave({
        ...formData,
        // For agent_mode, allToolsEnabled is always true, so this keeps sending
        // null and leaves the stored row untouched. Writing [] here instead
        // would stick (nothing resyncs it back) and misrepresent the agent.
        allowed_tools: allToolsEnabled ? null : formData.allowed_tools,
      });
      onClose();
    } catch (e) {
      // The parent rethrows so the error surfaces here, inside the modal. It
      // must not go to the page-level `error` state, which renders as a
      // full-page replacement and would discard the admin's unsaved edits.
      setSaveError(getApiErrorMessage(e, 'Failed to save agent'));
    } finally {
      setSaving(false);
    }
  };

  const toggleTool = (toolName: string) => {
    if (formData.allowed_tools.includes(toolName)) {
      setFormData(prev => ({
        ...prev,
        allowed_tools: prev.allowed_tools.filter(t => t !== toolName),
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        allowed_tools: [...prev.allowed_tools, toolName],
      }));
    }
  };

  const toggleApprovalRequired = (toolName: string) => {
    const current = formData.constraints.require_approval;
    if (current.includes(toolName)) {
      setFormData(prev => ({
        ...prev,
        constraints: {
          ...prev.constraints,
          require_approval: current.filter(t => t !== toolName),
        },
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        constraints: {
          ...prev.constraints,
          require_approval: [...current, toolName],
        },
      }));
    }
  };

  const addSuggestion = () => {
    if (newSuggestion.label && newSuggestion.prompt) {
      setFormData(prev => ({
        ...prev,
        suggestions: [...prev.suggestions, newSuggestion],
      }));
      setNewSuggestion({ label: '', prompt: '' });
    }
  };

  const removeSuggestion = (index: number) => {
    setFormData(prev => ({
      ...prev,
      suggestions: prev.suggestions.filter((_, i) => i !== index),
    }));
  };

  const isToolEnabled = (toolName: string) =>
    allToolsEnabled || formData.allowed_tools.includes(toolName);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/45 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-[var(--modal-header-background)] px-6 py-4 text-[var(--modal-header-foreground)]">
          <h2 className="text-xl font-semibold">
            {isNew ? 'Create Agent' : `Edit: ${agentData?.display_name}`}
          </h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="rounded-full opacity-70 hover:bg-current/10 hover:opacity-100"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Name (slug)
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                disabled={!isNew}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground disabled:bg-muted"
                placeholder="my_agent"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Display Name
              </label>
              <input
                type="text"
                value={formData.display_name}
                onChange={e => setFormData(prev => ({ ...prev, display_name: e.target.value }))}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
                placeholder="My Agent"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Description
            </label>
            <input
              type="text"
              value={formData.description}
              onChange={e => setFormData(prev => ({ ...prev, description: e.target.value }))}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
              placeholder="What this agent does..."
            />
          </div>

          <div>
            <label htmlFor="agent-system-prompt" className="mb-1 block text-sm font-medium text-foreground">
              System Prompt
            </label>
            <textarea
              id="agent-system-prompt"
              value={formData.system_prompt}
              onChange={e => setFormData(prev => ({ ...prev, system_prompt: e.target.value }))}
              rows={6}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 font-mono text-sm text-foreground"
              placeholder="You are a helpful assistant..."
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Variables: {'{{org_name}}'}, {'{{entity_type}}'}, {'{{entity_name}}'}, {'{{entity_id}}'}
            </p>
          </div>

          {/* Model Selection */}
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Model
            </label>
            {modelsLoading ? (
              <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading models...
              </div>
            ) : modelGroups.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-warning bg-warning-subtle rounded-lg p-3">
                <AlertCircle className="w-4 h-4" />
                No models available. Please configure API keys in Settings → API Keys.
              </div>
            ) : (
              <Combobox<ModelOption>
                items={modelGroups}
                value={selectedModel}
                onValueChange={model => setFormData(prev => ({
                  ...prev,
                  model_override: model?.value || null,
                }))}
                itemToStringLabel={model => model.label}
                itemToStringValue={model => model.value}
                isItemEqualToValue={(item, value) => item.value === value.value}
                filter={(model, query) => {
                  const normalizedQuery = query.trim().toLowerCase();
                  if (!normalizedQuery) return true;
                  return [model.label, model.value, model.providerName]
                    .some(value => value.toLowerCase().includes(normalizedQuery));
                }}
              >
                <ComboboxInput
                  placeholder="Use organization default or search models…"
                  aria-label="Search and select an agent model"
                  className="w-full"
                  showClear
                />
                <ComboboxContent>
                  <ComboboxEmpty>No models match your search.</ComboboxEmpty>
                  <ComboboxList>
                    {(group: ModelOptionGroup) => (
                      <ComboboxGroup key={group.value} items={group.items} className="pb-1 last:pb-0">
                        <ComboboxLabel className="sticky top-0 z-10 bg-popover font-medium">
                          {group.value}
                        </ComboboxLabel>
                        <ComboboxCollection>
                          {(model: ModelOption) => (
                            <ComboboxItem key={model.value} value={model} className="py-2">
                              <span className="min-w-0">
                                <span className="block truncate">{model.label}</span>
                                {model.label !== model.value && (
                                  <span className="block truncate text-xs text-muted-foreground">
                                    {model.value}
                                  </span>
                                )}
                              </span>
                            </ComboboxItem>
                          )}
                        </ComboboxCollection>
                      </ComboboxGroup>
                    )}
                  </ComboboxList>
                </ComboboxContent>
              </Combobox>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              {formData.model_override ? `Selected: ${formData.model_override}` : 'Uses the default model configured for your organization.'}
            </p>
          </div>

          {/* Execution Limits */}
          <div>
            <label htmlFor="agent-max-turns" className="mb-1 block text-sm font-medium text-foreground">
              Maximum turns
            </label>
            <input
              id="agent-max-turns"
              type="number"
              min={1}
              max={20}
              step={1}
              value={formData.constraints.max_iterations}
              onChange={e => {
                const parsedValue = Number.parseInt(e.target.value, 10);
                setFormData(prev => ({
                  ...prev,
                  constraints: {
                    ...prev.constraints,
                    max_iterations: Number.isNaN(parsedValue) ? 10 : Math.min(20, Math.max(1, parsedValue)),
                  },
                }));
              }}
              className="w-32 rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Maximum model and tool-call loop turns allowed for one response (1–20). Higher values can increase latency and cost.
            </p>
          </div>

          {/* Tools */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">
                Tools ({allToolsEnabled ? `all ${tools.length}` : formData.allowed_tools.length} enabled)
              </label>
              {hasAllToolsGrant && (
                <span
                  className="flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                  title="This assistant is always granted every tool. The list is shown for reference and cannot be narrowed here."
                >
                  <Lock className="w-3 h-3" />
                  All Tools
                </span>
              )}
            </div>
            <div className="relative mb-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={toolQuery}
                onChange={(e) => setToolQuery(e.target.value)}
                placeholder="Search tools…"
                aria-label="Search tools by name"
                className="h-9 w-full rounded-lg border border-border bg-background pl-9 pr-3 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring/30"
              />
            </div>
            <div className="max-h-64 overflow-y-auto rounded-lg border border-border divide-y divide-border/70">
              {tools.length > 0 && visibleTools.length === 0 && (
                <div className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No tools match "{toolQuery}".
                </div>
              )}
              {visibleTools.map(tool => {
                const toolId = tool.id || tool.name;
                const enabled = isToolEnabled(toolId);
                const requiresApproval = formData.constraints.require_approval.includes(toolId);
                return (
                  <div key={toolId} className={`flex items-center justify-between px-4 py-2 hover:bg-muted/40 ${allToolsEnabled ? 'opacity-80' : ''}`}>
                    <div className="flex items-center gap-3">
                      <Button variant="primary"
                        onClick={() => !allToolsEnabled && toggleTool(toolId)}
                        disabled={allToolsEnabled}
                        className={`flex h-5 w-5 items-center justify-center rounded border transition-colors ${
                          enabled
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-input bg-background text-transparent'
                        } ${allToolsEnabled ? 'cursor-default' : ''}`}
                      >
                        {enabled && <Check className="w-3 h-3" />}
                      </Button>
                      <div>
                        <div className="text-sm font-medium text-foreground">{tool.display_name || tool.name}</div>
                        <div className="text-xs text-muted-foreground">{tool.description}</div>
                      </div>
                    </div>
                    <Button variant="primary"
                      onClick={() => toggleApprovalRequired(toolId)}
                      disabled={!enabled || allToolsEnabled}
                      className={`flex items-center gap-1 px-2 py-1 rounded text-xs ${
                        requiresApproval
                          ? 'bg-warning-subtle text-warning'
                          : 'bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      } ${(!enabled || allToolsEnabled) ? 'opacity-50' : ''}`}
                    >
                      <Lock className="w-3 h-3" />
                      {requiresApproval ? 'Approval Required' : 'Auto'}
                    </Button>
                  </div>
                );
              })}
            </div>
            {allToolsEnabled && (
              <p className="mt-1 text-xs text-muted-foreground">
                This assistant is always granted every tool, so the list above is read-only.
                Every other setting on this page can be changed. To stop a specific tool from
                being used, disable it for the organization under Settings → MCP Tools.
              </p>
            )}
          </div>

          {/* Suggestions */}
          <div>
            <label className="mb-2 block text-sm font-medium text-foreground">
              Quick Start Suggestions
            </label>
            <div className="space-y-2">
              {formData.suggestions.map((s, i) => (
                <div key={i} className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2">
                  <span className="text-sm font-medium text-foreground">{s.label}:</span>
                  <span className="flex-1 truncate text-sm text-muted-foreground">{s.prompt}</span>
                  <Button
                    variant="ghost"
                    onClick={() => removeSuggestion(i)}
                    className="text-muted-foreground transition-colors hover:text-destructive"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              ))}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newSuggestion.label}
                  onChange={e => setNewSuggestion(prev => ({ ...prev, label: e.target.value }))}
                  placeholder="Label"
                  className="w-32 rounded border border-input bg-background px-2 py-1 text-sm text-foreground"
                />
                <input
                  type="text"
                  value={newSuggestion.prompt}
                  onChange={e => setNewSuggestion(prev => ({ ...prev, prompt: e.target.value }))}
                  placeholder="Prompt text..."
                  className="flex-1 rounded border border-input bg-background px-2 py-1 text-sm text-foreground"
                />
                <Button
                  onClick={addSuggestion}
                  disabled={!newSuggestion.label || !newSuggestion.prompt}
                  variant="secondary"
                  size="sm"
                >
                  Add
                </Button>
              </div>
            </div>
          </div>

          {/* Active Toggle */}
          <div className="flex items-center gap-3">
            <Button variant="primary"
              onClick={() => setFormData(prev => ({ ...prev, is_active: !prev.is_active }))}
              // Agent Mode must stay active: a disabled definition makes every
              // Agent Mode run fail, while the chat UI silently falls back to an
              // arbitrary agent. The backend rejects it too; this just keeps the
              // admin from reaching an error they cannot act on.
              disabled={hasAllToolsGrant}
              aria-label={hasAllToolsGrant ? 'Active (locked for this assistant)' : 'Active'}
              title={
                hasAllToolsGrant
                  ? 'The Agent Mode assistant cannot be deactivated.'
                  : undefined
              }
              className={`flex h-5 w-5 items-center justify-center rounded border transition-colors ${
                formData.is_active
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-input bg-background text-transparent'
              } ${hasAllToolsGrant ? 'cursor-default opacity-70' : ''}`}
            >
              {formData.is_active && <Check className="w-3 h-3" />}
            </Button>
            <span className="text-sm text-foreground">Active</span>
          </div>
        </div>

        {/* Save error — lives here, outside the scroll container, so it is always
            visible; routing it to the page-level error state would unmount this
            modal and discard the admin's edits. */}
        {saveError && (
          <div className="shrink-0 px-6 pb-3">
            <AlertBanner tone="error" size="sm">{saveError}</AlertBanner>
          </div>
        )}

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-border bg-muted/30 px-6 py-4">
          <Button
            onClick={onClose}
            variant="ghost"
          >
            Cancel
          </Button>
          <Button variant="primary"
            onClick={handleSave}
            disabled={!formData.name || !formData.display_name || !formData.system_prompt}
            loading={saving}
          >
            {isNew ? 'Create Agent' : 'Save Changes'}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface TestConversationMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  createdAt: string;
  toolCalls: ToolCallInfo[];
  pendingActions: PendingAction[];
  tokensUsed: number;
  error?: string | null;
  raw: Record<string, unknown>;
}

function mapSessionMessage(message: AgentMessage): TestConversationMessage {
  return {
    id: message.message_id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    toolCalls: message.tool_calls || [],
    pendingActions: message.pending_actions || [],
    tokensUsed: message.tokens_used,
    error: null,
    raw: message as unknown as Record<string, unknown>,
  };
}

function TestConversationBubble({ message }: { message: TestConversationMessage }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser
            ? 'bg-cobalt text-white rounded-br-md'
            : 'bg-card border border-border text-foreground rounded-bl-md'
        }`}
      >
        <div className="text-sm whitespace-pre-wrap">{message.content}</div>

        {!isUser && (
          <details className="mt-3 rounded-lg border border-border bg-muted/50">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
              Debug Details
            </summary>
            <div className="space-y-3 border-t border-border px-3 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="default">{message.tokensUsed} tokens</Badge>
                {message.toolCalls.length > 0 && <Badge variant="ai">{message.toolCalls.length} tool calls</Badge>}
                {message.pendingActions.length > 0 && (
                  <Badge variant="warning">{message.pendingActions.length} pending actions</Badge>
                )}
                {message.error && <Badge variant="error">Error</Badge>}
              </div>

              <div>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Tool Calls
                </div>
                <pre className="overflow-x-auto rounded-lg bg-card p-2 text-xs text-foreground">
                  {JSON.stringify(message.toolCalls, null, 2)}
                </pre>
              </div>

              <div>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Pending Actions
                </div>
                <pre className="overflow-x-auto rounded-lg bg-card p-2 text-xs text-foreground">
                  {JSON.stringify(message.pendingActions, null, 2)}
                </pre>
              </div>

              {message.error && (
                <div>
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-destructive">
                    Error
                  </div>
                  <pre className="overflow-x-auto rounded-lg bg-destructive-subtle p-2 text-xs text-destructive">
                    {message.error}
                  </pre>
                </div>
              )}

              <div>
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Raw Message JSON
                </div>
                <pre className="overflow-x-auto rounded-lg bg-card p-2 text-xs text-foreground">
                  {JSON.stringify(message.raw, null, 2)}
                </pre>
              </div>
            </div>
          </details>
        )}

        <div className={`mt-2 text-[10px] ${isUser ? 'text-white/70' : 'text-muted-foreground'}`}>
          {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}

export default function AgentsTab() {
  const { selectedOrgId } = useOrgSelector();
  const testMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const [agents, setAgents] = useState<AgentDefinitionListItem[]>([]);
  const [tools, setTools] = useState<AgentToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingAgent, setEditingAgent] = useState<AgentDefinition | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [availableModels, setAvailableModels] = useState<ProviderModels[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [testPanelOpen, setTestPanelOpen] = useState(false);
  const [testAgentName, setTestAgentName] = useState('');
  const [testPrompt, setTestPrompt] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testSessionId, setTestSessionId] = useState<string | null>(null);
  const [testMessages, setTestMessages] = useState<TestConversationMessage[]>([]);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionListLoading, setSessionListLoading] = useState(false);
  const [agentTestSessions, setAgentTestSessions] = useState<Array<{ session_id: string; title: string | null; updated_at: string; message_count: number; total_tokens: number }>>([]);
  const [testSessionsByAgent, setTestSessionsByAgent] = useState<Record<string, string>>({});

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      // Definitions are the source of truth for this tab; load them first so a
      // missing tool manifest never blocks the admin view.
      const agentsData = await agent.listDefinitions(!showInactive, true);
      setAgents(agentsData);
      try {
        const mcpData = await mcp.getTooling();
        setTools(
          mcpData.capabilities
            .filter(capability => capability.package_enabled && capability.is_enabled && capability.is_active)
            .map(capability => ({
              id: capability.id,
              name: capability.capability_key,
              display_name: capability.display_name,
              description: capability.description,
              category: capability.category,
              is_mutating: capability.is_mutating,
              requires_approval: capability.requires_approval,
              is_enabled: capability.is_enabled,
              package_enabled: capability.package_enabled,
              parameters: capability.input_schema,
            }))
        );
      } catch (toolingError) {
        // MCP tooling is optional for the agents list; degrade to no tools but
        // log so the failure is diagnosable in production rather than silent.
        console.error('Failed to load MCP tooling for agent editor:', toolingError);
        setTools([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  const fetchModels = useCallback(async () => {
    try {
      setModelsLoading(true);
      const result = await aiFeatures.getModels(selectedOrgId);
      setAvailableModels(result.providers);
    } catch (e) {
      console.error('Failed to load models:', e);
    } finally {
      setModelsLoading(false);
    }
  }, [selectedOrgId]);

  useEffect(() => {
    fetchData();
    fetchModels();
  }, [fetchData, fetchModels]);

  useEffect(() => {
    if (!agents.length) {
      setTestAgentName('');
      return;
    }
    if (!testAgentName || !agents.some(agentItem => agentItem.name === testAgentName)) {
      setTestAgentName(agents[0].name);
    }
  }, [agents, testAgentName]);

  useEffect(() => {
    testMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [testMessages, testLoading, sessionLoading, testPanelOpen]);

  const hydrateSession = useCallback(
    async (sessionId: string) => {
      try {
        setSessionLoading(true);
        const session = await agent.getSession(sessionId);
        setTestMessages(session.messages.map(mapSessionMessage));
      } catch {
        // Session history is not part of the phase-1 runtime yet.
        setTestMessages([]);
      } finally {
        setSessionLoading(false);
      }
    },
    []
  );

  const loadAgentSessions = useCallback(
    async (agentName: string) => {
      const selectedAgent = agents.find(agentItem => agentItem.name === agentName);
      if (!selectedAgent) {
        setAgentTestSessions([]);
        return;
      }
      try {
        setSessionListLoading(true);
        const sessions = await agent.listSessions(50, 0);
        const filtered = sessions
          .filter(session => session.definition_id === selectedAgent.definition_id)
          .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
          .map(session => ({
            session_id: session.session_id,
            title: session.title,
            updated_at: session.updated_at,
            message_count: session.message_count,
            total_tokens: session.total_tokens,
          }));
        setAgentTestSessions(filtered);
      } catch {
        // Session history is not part of the phase-1 runtime yet.
        setAgentTestSessions([]);
      } finally {
        setSessionListLoading(false);
      }
    },
    [agents]
  );

  const openTestPanel = useCallback(
    async (agentName: string) => {
      setTestAgentName(agentName);
      setTestPanelOpen(true);
      setTestError(null);
      await loadAgentSessions(agentName);
      const existingSessionId = testSessionsByAgent[agentName] || null;
      setTestSessionId(existingSessionId);
      if (existingSessionId) {
        await hydrateSession(existingSessionId);
      } else {
        setTestMessages([]);
      }
    },
    [hydrateSession, loadAgentSessions, testSessionsByAgent]
  );

  const handleEdit = async (definitionId: string) => {
    try {
      const data = await agent.getDefinition(definitionId);
      setEditingAgent(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load agent');
    }
  };

  // Contract: this must REJECT on failure. AgentEditor.handleSave catches and
  // renders the message inside the modal. Do not add a try/catch that routes to
  // `setError` here — that renders as a full-page replacement (see the `error`
  // branch below) and would unmount the editor, discarding the admin's edits.
  const handleSave = async (data: Partial<AgentDefinition>) => {
    if (isCreating) {
      await agent.createDefinition(data as any);
    } else if (editingAgent) {
      await agent.updateDefinition(editingAgent.definition_id, data as any);
    }
    setEditingAgent(null);
    setIsCreating(false);
    fetchData();
  };

  const handleDelete = async (definitionId: string) => {
    if (!confirm('Are you sure you want to delete this agent?')) return;
    try {
      await agent.deleteDefinition(definitionId);
      fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete agent');
    }
  };

  const handleTestAgent = async () => {
    if (!testAgentName || !testPrompt.trim()) return;
    try {
      setTestLoading(true);
      setTestError(null);
      const outgoingMessage: TestConversationMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: testPrompt.trim(),
        createdAt: new Date().toISOString(),
        toolCalls: [],
        pendingActions: [],
        tokensUsed: 0,
        raw: { role: 'user', content: testPrompt.trim() },
      };
      setTestMessages(prev => [...prev, outgoingMessage]);
      const prompt = testPrompt.trim();
      setTestPrompt('');
      const selectedAgent = agents.find(agentItem => agentItem.name === testAgentName);
      if (!selectedAgent) {
        throw new Error('Select an agent before sending a test prompt');
      }
      const result = await agent.createRun({
        definition_id: selectedAgent.definition_id,
        input: prompt,
        session_id: testSessionId || undefined,
      });
      if (result.session_id) {
        setTestSessionId(result.session_id);
        setTestSessionsByAgent(prev => ({ ...prev, [testAgentName]: result.session_id as string }));
      }
      setTestMessages(prev => [
        ...prev,
        {
          id: result.run_id,
          role: 'agent',
          content: result.output || result.error || 'Agent run completed without a response.',
          createdAt: result.completed_at || result.updated_at || result.created_at,
          toolCalls: [],
          pendingActions: [],
          tokensUsed: Number(result.metadata?.tokens_used || 0),
          error: result.status === 'failed' ? result.error || 'Agent run failed' : null,
          raw: result as unknown as Record<string, unknown>,
        },
      ]);
      await loadAgentSessions(testAgentName);
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : 'Failed to test agent';
      setTestError(errorMessage);
      setTestMessages(prev => [
        ...prev,
        {
          id: `agent-error-${Date.now()}`,
          role: 'agent',
          content: errorMessage,
          createdAt: new Date().toISOString(),
          toolCalls: [],
          pendingActions: [],
          tokensUsed: 0,
          error: errorMessage,
          raw: { error: errorMessage },
        },
      ]);
    } finally {
      setTestLoading(false);
    }
  };

  const resetTestSession = () => {
    if (!testAgentName) return;
    setTestSessionId(null);
    setTestMessages([]);
    setTestError(null);
    setTestSessionsByAgent(prev => {
      const next = { ...prev };
      delete next[testAgentName];
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-cobalt animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-destructive mb-4">{error}</p>
        <Button variant="primary" onClick={fetchData} className="px-4 py-2 bg-cobalt text-white rounded-lg">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-muted-foreground" />
            <h2 className="text-lg font-medium text-foreground">AI Agents</h2>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
              className="rounded border-border"
            />
            Show inactive
          </label>
        </div>
        <Button variant="primary"
          onClick={() => {
            setIsCreating(true);
            setEditingAgent({} as AgentDefinition);
          }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg"
        >
          <Plus className="w-4 h-4" />
          New Agent
        </Button>
      </div>

      {/* Agents List */}
      {agents.length === 0 ? (
        <div className="bg-card rounded-xl border border-border p-8 text-center">
          <Bot className="w-12 h-12 text-muted-foreground/60 mx-auto mb-3" />
          <p className="text-muted-foreground mb-2">No agents configured</p>
          <p className="text-sm text-muted-foreground">
            Create an agent to enable AI-powered assistance.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {agents.map(a => (
            <div
              key={a.definition_id}
              className={`bg-card rounded-xl border border-border p-4 ${
                !a.is_active ? 'opacity-60' : ''
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-cobalt/10 rounded-lg flex items-center justify-center">
                    <Bot className="w-5 h-5 text-cobalt" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-foreground">{a.display_name}</span>
                      <code className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                        {a.name}
                      </code>
                      {a.is_system && <Badge variant="default">System</Badge>}
                      {a.is_active ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Badge variant="default">Inactive</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">{a.description}</p>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  {/* Stats */}
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Wrench className="w-4 h-4" />
                      {/* Only agent_mode is granted every tool; for everyone
                          else a count of 0 genuinely means no tools. */}
                      <span>{a.name === AGENT_MODE_NAME ? 'All' : a.tool_count} tools</span>
                    </div>
                    {a.approval_count > 0 && (
                      <div className="flex items-center gap-1 text-warning">
                        <Lock className="w-4 h-4" />
                        <span>{a.approval_count} require approval</span>
                      </div>
                    )}
                    {a.suggestion_count > 0 && (
                      <div className="flex items-center gap-1">
                        <Sparkles className="w-4 h-4" />
                        <span>{a.suggestion_count} suggestions</span>
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => openTestPanel(a.name)}
                      className="inline-flex items-center gap-2 px-3 py-2 text-sm text-cobalt hover:bg-cobalt/5 rounded-lg"
                    >
                      <Play className="w-4 h-4" />
                      Run Test
                    </Button>
                    <Button
                      variant="ghost-action"
                      size="icon"
                      aria-label={`Edit ${a.display_name}`}
                      onClick={() => handleEdit(a.definition_id)}
                      className="text-muted-foreground"
                    >
                      <Edit className="w-4 h-4" />
                    </Button>
                    {!a.is_system && (
                      <Button
                        variant="ghost-danger"
                        size="icon"
                        aria-label={`Delete ${a.display_name}`}
                        onClick={() => handleDelete(a.definition_id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Editor Modal */}
      {editingAgent && (
        <AgentEditor
          agent={isCreating ? null : editingAgent}
          tools={tools}
          availableModels={availableModels}
          modelsLoading={modelsLoading}
          onSave={handleSave}
          onClose={() => {
            setEditingAgent(null);
            setIsCreating(false);
          }}
          isNew={isCreating}
        />
      )}

      {testPanelOpen && (
        <div className="fixed inset-y-0 right-0 z-40 w-full max-w-2xl border-l border-border bg-card shadow-2xl">
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-cobalt" />
                  <h3 className="text-base font-medium text-foreground">Agent Test Console</h3>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Conversation-style debug interface backed by persisted agent sessions.
                </p>
              </div>
              <div className="flex items-center gap-2">
                {testSessionId && <Badge variant="cobalt">Session {testSessionId.slice(0, 8)}</Badge>}
                <Button variant="primary"
                  onClick={() => setTestPanelOpen(false)}
                  className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-muted-foreground"
                >
                  <PanelRightClose className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="border-b border-border px-5 py-4">
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto]">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Agent</label>
                  <select
                    value={testAgentName}
                    onChange={async e => {
                      await openTestPanel(e.target.value);
                    }}
                    className="w-full rounded-lg border border-border px-3 py-2 text-sm"
                  >
                    {agents.map(agentItem => (
                      <option key={agentItem.definition_id} value={agentItem.name}>
                        {agentItem.display_name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-end gap-2">
                  <Button variant="ghost"
                    onClick={resetTestSession}
                    className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-foreground hover:bg-muted/50"
                  >
                    <RefreshCcw className="h-4 w-4" />
                    New Test Session
                  </Button>
                </div>
              </div>
            </div>

            <div className="flex flex-1 overflow-hidden bg-muted/50">
              <div className="w-72 shrink-0 border-r border-border bg-card px-4 py-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Session History
                </div>
                {sessionListLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading sessions...
                  </div>
                ) : agentTestSessions.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                    No saved sessions for this agent yet.
                  </div>
                ) : (
                  <div className="space-y-2 overflow-y-auto">
                    {agentTestSessions.map(session => (
                      <Button variant="primary"
                        key={session.session_id}
                        onClick={async () => {
                          setTestSessionId(session.session_id);
                          setTestSessionsByAgent(prev => ({ ...prev, [testAgentName]: session.session_id }));
                          await hydrateSession(session.session_id);
                        }}
                        className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                          testSessionId === session.session_id
                            ? 'border-cobalt bg-cobalt/5'
                            : 'border-border bg-card hover:bg-muted/50'
                        }`}
                      >
                        <div className="text-sm font-medium text-foreground">
                          {session.title || `Session ${session.session_id.slice(0, 8)}`}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">
                          {new Date(session.updated_at).toLocaleString()}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                          <span>{session.message_count} messages</span>
                          <span>{session.total_tokens} tokens</span>
                        </div>
                      </Button>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex-1 overflow-y-auto px-5 py-5">
                {sessionLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading conversation...
                  </div>
                ) : testMessages.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border bg-card px-6 py-10 text-center">
                    <PanelRightOpen className="mx-auto mb-3 h-8 w-8 text-muted-foreground/60" />
                    <p className="text-sm text-muted-foreground">Start a test conversation with this agent.</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      The panel will keep the same backend session id for follow-up messages.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {testMessages.map(message => (
                      <TestConversationBubble key={message.id} message={message} />
                    ))}
                    {testLoading && (
                      <div className="flex justify-start">
                        <div className="rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3 shadow-sm">
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Agent is thinking...
                          </div>
                        </div>
                      </div>
                    )}
                    <div ref={testMessagesEndRef} />
                  </div>
                )}
              </div>
            </div>

            <div className="border-t border-border px-5 py-4">
              {testError && (
                <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive-subtle px-4 py-3 text-sm text-destructive">
                  {testError}
                </div>
              )}
              <div className="flex gap-3">
                <textarea
                  value={testPrompt}
                  onChange={e => setTestPrompt(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      void handleTestAgent();
                    }
                  }}
                  rows={3}
                  disabled={testLoading || !testAgentName}
                  className="flex-1 rounded-lg border border-border px-3 py-2 text-sm"
                  placeholder="Send a follow-up question. The current session id will be reused."
                />
                <Button variant="primary"
                  onClick={handleTestAgent}
                  disabled={testLoading || !testAgentName || !testPrompt.trim()}
                  className="inline-flex items-center gap-2 self-end rounded-lg bg-cobalt px-4 py-2 text-white hover:bg-cobalt-dark disabled:opacity-50"
                >
                  {testLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronRight className="h-4 w-4" />}
                  Send
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
