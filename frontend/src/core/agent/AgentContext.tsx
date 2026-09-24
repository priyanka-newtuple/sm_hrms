import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { agent as agentApi } from '../services/api';
import { workflowEntityKeys } from '../services/api/queryKeys';
import { AGENT_MODE_NAME } from '../constants/agents';
import type {
  AgentDefinitionListItem,
  PendingAction as APIPendingAction,
  ToolCallInfo,
  AgentMessage as APIAgentMessage,
  AgentRun,
} from '../types';

const AGENT_SIDEBAR_DEFAULT_WIDTH = 384;
const AGENT_SIDEBAR_MIN_WIDTH = 320;
const AGENT_SIDEBAR_MAX_WIDTH = 720;
const AGENT_SIDEBAR_WIDTH_STORAGE_KEY = 'agent-sidebar-width';

function clampAgentSidebarWidth(width: number): number {
  return Math.min(AGENT_SIDEBAR_MAX_WIDTH, Math.max(AGENT_SIDEBAR_MIN_WIDTH, width));
}

function getInitialAgentSidebarWidth(): number {
  if (typeof window === 'undefined') return AGENT_SIDEBAR_DEFAULT_WIDTH;
  const stored = Number(window.localStorage.getItem(AGENT_SIDEBAR_WIDTH_STORAGE_KEY));
  return Number.isFinite(stored)
    ? clampAgentSidebarWidth(stored)
    : AGENT_SIDEBAR_DEFAULT_WIDTH;
}

// Types for the agent system
export interface PinnedEntity {
  id: string;
  type: 'Job' | 'Candidate' | 'Application';
  label: string;
}

export interface ToolExecution {
  name: string;
  input?: Record<string, unknown>;
  output?: string;
  status: 'running' | 'success' | 'error';
  duration_ms?: number;
}

export interface PendingActionUI {
  action_id: string;
  type: string;
  description: string;
  args: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected';
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent' | 'system';
  content: string;
  timestamp: Date;
  toolExecutions?: ToolExecution[];
  pendingActions?: PendingActionUI[];
}

export interface ConversationThread {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
  messages: ChatMessage[];
  pinnedEntities: PinnedEntity[];
  definitionId?: string;
  agentName?: string;
}

interface AgentUIState {
  // Sidebar state
  isOpen: boolean;
  activeTab: 'chat' | 'history';
  sidebarWidth: number;

  // Available agents
  agentDefinitions: AgentDefinitionListItem[];
  selectedAgentId: string | null;

  // Current conversation
  currentThread: ConversationThread | null;
  threads: ConversationThread[];

  // Context tracking
  pinnedEntities: PinnedEntity[];

  // Agent state
  isThinking: boolean;
  isLoadingDefinitions: boolean;
  isLoadingSessions: boolean;

  // Error state
  error: string | null;

  // UI focus (what the agent is pointing to)
  agentFocus: {
    entityId?: string;
    path?: string;
  } | null;
}

interface AgentContextValue extends AgentUIState {
  // Sidebar controls
  toggleSidebar: () => void;
  openSidebar: () => void;
  closeSidebar: () => void;
  setActiveTab: (tab: 'chat' | 'history') => void;
  setSidebarWidth: (width: number) => void;

  // Agent selection
  selectAgent: (definitionId: string) => void;

  // Message handling
  sendMessage: (content: string) => Promise<void>;

  // Context management
  pinEntity: (entity: PinnedEntity) => void;
  unpinEntity: (entityId: string) => void;
  clearPinnedEntities: () => void;

  // Thread management
  /** Resolves `true` once the thread is applied, `false` on failure or if a
   *  newer selectThread/startNewThread call superseded it mid-fetch. */
  selectThread: (threadId: string) => Promise<boolean>;
  startNewThread: () => void;
  loadSessions: () => Promise<void>;
  renameThread: (threadId: string, title: string) => Promise<void>;
  deleteThread: (threadId: string) => Promise<void>;

  // Action approval
  approveAction: (messageId: string, actionId: string) => Promise<void>;
  rejectAction: (messageId: string, actionId: string) => Promise<void>;

  // Agent focus
  setAgentFocus: (focus: AgentUIState['agentFocus']) => void;
  clearAgentFocus: () => void;

  // Quick start suggestions for current agent
  getSuggestions: () => { id: string; label: string; prompt: string }[];
}

const AgentContext = createContext<AgentContextValue | null>(null);

// Generate unique IDs (fallback for local-only messages)
const generateId = () => `local-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// Convert API tool calls to UI format
function convertToolCalls(toolCalls: ToolCallInfo[] | null): ToolExecution[] | undefined {
  if (!toolCalls || toolCalls.length === 0) return undefined;
  return toolCalls.map(tc => ({
    name: tc.tool,
    input: tc.args,
    output: tc.result ? JSON.stringify(tc.result, null, 2) : undefined,
    status: tc.success ? 'success' : 'error',
    duration_ms: tc.duration_ms,
  }));
}

// Convert API pending actions to UI format
function convertPendingActions(actions: APIPendingAction[] | null): PendingActionUI[] | undefined {
  if (!actions || actions.length === 0) return undefined;
  return actions.map(a => ({
    action_id: a.action_id,
    type: a.tool,
    description: a.description,
    args: a.args,
    status: a.status,
  }));
}

// Convert API messages to UI format
function convertAPIMessage(msg: APIAgentMessage): ChatMessage {
  return {
    id: msg.message_id,
    role: msg.role,
    content: msg.content,
    timestamp: new Date(msg.created_at),
    toolExecutions: convertToolCalls(msg.tool_calls),
    pendingActions: convertPendingActions(msg.pending_actions),
  };
}

function metadataList<T>(metadata: Record<string, unknown>, key: string): T[] | null {
  const value = metadata[key];
  return Array.isArray(value) ? (value as T[]) : null;
}

function createAgentMessageFromRun(run: AgentRun): ChatMessage {
  const completedAt = run.completed_at || run.updated_at || run.started_at || run.created_at;
  return {
    id: run.run_id,
    role: 'agent',
    content: run.output || run.error || 'Agent run completed without a response.',
    timestamp: new Date(completedAt),
    toolExecutions: convertToolCalls(metadataList<ToolCallInfo>(run.metadata, 'tool_calls')),
    pendingActions: convertPendingActions(metadataList<APIPendingAction>(run.metadata, 'pending_actions')),
  };
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AgentUIState>({
    isOpen: false,
    activeTab: 'chat',
    sidebarWidth: getInitialAgentSidebarWidth(),
    agentDefinitions: [],
    selectedAgentId: null,
    currentThread: null,
    threads: [],
    pinnedEntities: [],
    isThinking: false,
    isLoadingDefinitions: true,
    isLoadingSessions: false,
    error: null,
    agentFocus: null,
  });

  const queryClient = useQueryClient();

  // Bumped by every call that changes/replaces `currentThread` (selectThread,
  // startNewThread). `selectThread` captures its own value before the async
  // `getSession` fetch and checks it still matches after — if a newer call
  // (the user picking another thread, or "New conversation", or a second
  // concurrent restore) has already landed, the slower/stale response is
  // dropped instead of clobbering the newer state. See STAT-334 review: a
  // slow mount-time session-restore fetch could otherwise overwrite a thread
  // the user switched to while it was still in flight.
  const threadRequestRef = useRef(0);

  // Per-agent start-screen suggestion chips. listDefinitions only returns a
  // suggestion_count, so the full definition is fetched when the selected agent
  // changes (falls back to sensible defaults when an agent defines none).
  const [agentSuggestions, setAgentSuggestions] = useState<{ label: string; prompt: string }[]>([]);

  // Load agent definitions on mount
  useEffect(() => {
    loadAgentDefinitions();
  }, []);

  // Fetch the selected agent's own suggestions for the start screen.
  useEffect(() => {
    const definitionId = state.selectedAgentId;
    if (!definitionId) {
      setAgentSuggestions([]);
      return;
    }
    let cancelled = false;
    agentApi
      .getDefinition(definitionId)
      .then(def => {
        if (!cancelled) setAgentSuggestions(def.suggestions ?? []);
      })
      .catch(() => {
        if (!cancelled) setAgentSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [state.selectedAgentId]);

  const loadAgentDefinitions = async () => {
    try {
      setState(prev => ({ ...prev, isLoadingDefinitions: true, error: null }));

      // Single call with include_agent_mode — avoids race condition on
      // new orgs where parallel requests both try to seed definitions.
      const definitions = await agentApi.listDefinitions(true, true);

      // Default to agent_mode if present, otherwise first agent
      const agentMode = definitions.find(d => d.name === AGENT_MODE_NAME);
      const defaultId = agentMode?.definition_id ?? definitions[0]?.definition_id;

      setState(prev => ({
        ...prev,
        agentDefinitions: definitions,
        selectedAgentId: prev.selectedAgentId || defaultId,
        isLoadingDefinitions: false,
      }));
    } catch (e) {
      console.error('Failed to load agent definitions:', e);
      setState(prev => ({
        ...prev,
        isLoadingDefinitions: false,
        error: 'Failed to load agent definitions',
      }));
    }
  };

  const loadSessions = useCallback(async () => {
    try {
      setState(prev => ({ ...prev, isLoadingSessions: true }));
      const sessions = await agentApi.listSessions(20, 0);

      // Convert API sessions to threads (without messages for now)
      const threads: ConversationThread[] = sessions.map(s => ({
        id: s.session_id,
        title: s.title || 'Untitled conversation',
        createdAt: new Date(s.created_at),
        updatedAt: new Date(s.updated_at),
        messages: [],
        pinnedEntities: [],
        definitionId: s.definition_id || undefined,
        agentName: s.agent_name || undefined,
      }));

      setState(prev => ({
        ...prev,
        threads,
        isLoadingSessions: false,
      }));
    } catch (e) {
      console.error('Failed to load sessions:', e);
      setState(prev => ({ ...prev, isLoadingSessions: false }));
    }
  }, []);

  const toggleSidebar = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: !prev.isOpen }));
  }, []);

  const openSidebar = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: true }));
  }, []);

  const closeSidebar = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: false }));
  }, []);

  const setActiveTab = useCallback((tab: 'chat' | 'history') => {
    setState(prev => ({ ...prev, activeTab: tab }));
    // Load sessions when switching to history tab
    if (tab === 'history') {
      loadSessions();
    }
  }, [loadSessions]);

  const setSidebarWidth = useCallback((width: number) => {
    const clampedWidth = clampAgentSidebarWidth(width);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(AGENT_SIDEBAR_WIDTH_STORAGE_KEY, String(clampedWidth));
    }
    setState(prev => ({ ...prev, sidebarWidth: clampedWidth }));
  }, []);

  const selectAgent = useCallback((definitionId: string) => {
    setState(prev => ({
      ...prev,
      selectedAgentId: definitionId,
      // Clear current thread when switching agents — new agent starts fresh
      currentThread: null,
    }));
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    // Get selected agent
    const selectedAgent = state.agentDefinitions.find(a => a.definition_id === state.selectedAgentId);
    if (!selectedAgent) {
      setState(prev => ({ ...prev, error: 'No agent selected' }));
      return;
    }

    // Create user message locally
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: new Date(),
    };

    // Update state with user message
    setState(prev => {
      if (!prev.currentThread) {
        // Create new thread
        const newThread: ConversationThread = {
          id: generateId(), // Will be replaced by session_id from API
          title: content.slice(0, 50) + (content.length > 50 ? '...' : ''),
          createdAt: new Date(),
          updatedAt: new Date(),
          messages: [userMessage],
          pinnedEntities: prev.pinnedEntities,
          definitionId: prev.selectedAgentId || undefined,
          agentName: selectedAgent.name,
        };
        return {
          ...prev,
          currentThread: newThread,
          isThinking: true,
          error: null,
        };
      }

      // Add to existing thread
      const updatedThread = {
        ...prev.currentThread,
        messages: [...prev.currentThread.messages, userMessage],
        updatedAt: new Date(),
      };
      return {
        ...prev,
        currentThread: updatedThread,
        isThinking: true,
        error: null,
      };
    });

    try {
      const currentSessionId =
        state.currentThread && !state.currentThread.id.startsWith('local-')
          ? state.currentThread.id
          : undefined;
      const run = await agentApi.createRun({
        definition_id: selectedAgent.definition_id,
        input: content,
        session_id: currentSessionId,
        context: {
          entities: state.pinnedEntities,
        },
      });

      const agentMessage = createAgentMessageFromRun(run);

      // The agent run may have created/enrolled/transitioned entities. Invalidate
      // the workflow-entities cache so any mounted board (the agent canvas board
      // AND the main pipeline page) refetches and reflects the change without a
      // manual reload.
      void queryClient.invalidateQueries({ queryKey: workflowEntityKeys.all() });

      setState(prev => {
        if (!prev.currentThread) return { ...prev, isThinking: false };

        const threadId = run.session_id || prev.currentThread.id;
        const updatedThread = {
          ...prev.currentThread,
          id: threadId,
          messages: [...prev.currentThread.messages, agentMessage],
          updatedAt: new Date(),
        };

        const existingIndex = prev.threads.findIndex(t => t.id === threadId);
        let updatedThreads: ConversationThread[];
        if (existingIndex >= 0) {
          updatedThreads = prev.threads.map((t, i) => i === existingIndex ? updatedThread : t);
        } else {
          updatedThreads = [updatedThread, ...prev.threads];
        }

        return {
          ...prev,
          currentThread: updatedThread,
          threads: updatedThreads,
          isThinking: false,
          error: run.status === 'failed' ? (run.error || 'Agent run failed') : null,
        };
      });
    } catch (e) {
      console.error('Failed to send message:', e);
      const errorMessage = e instanceof Error ? e.message : 'Failed to send message';

      // Add error message to thread
      const errorResponse: ChatMessage = {
        id: generateId(),
        role: 'agent',
        content: `Sorry, I encountered an error: ${errorMessage}. Please try again.`,
        timestamp: new Date(),
      };

      setState(prev => {
        if (!prev.currentThread) return { ...prev, isThinking: false, error: errorMessage };

        const updatedThread = {
          ...prev.currentThread,
          messages: [...prev.currentThread.messages, errorResponse],
          updatedAt: new Date(),
        };

        return {
          ...prev,
          currentThread: updatedThread,
          isThinking: false,
          error: errorMessage,
        };
      });
    }
  }, [state.agentDefinitions, state.selectedAgentId, state.currentThread, state.pinnedEntities, queryClient]);

  const pinEntity = useCallback((entity: PinnedEntity) => {
    setState(prev => {
      if (prev.pinnedEntities.find(e => e.id === entity.id)) {
        return prev;
      }
      return { ...prev, pinnedEntities: [...prev.pinnedEntities, entity] };
    });
  }, []);

  const unpinEntity = useCallback((entityId: string) => {
    setState(prev => ({
      ...prev,
      pinnedEntities: prev.pinnedEntities.filter(e => e.id !== entityId),
    }));
  }, []);

  const clearPinnedEntities = useCallback(() => {
    setState(prev => ({ ...prev, pinnedEntities: [] }));
  }, []);

  // Returns whether the thread was actually applied — `false` on a fetch
  // error, or when a newer `selectThread`/`startNewThread` call superseded
  // this one while its fetch was in flight (not itself an error, but still
  // not applied). Callers that silently retry/restore in the background
  // (see AgentModePage's mount-time session restore) need this to know
  // whether to surface a failure instead of leaving the UI looking normal.
  const selectThread = useCallback(async (threadId: string): Promise<boolean> => {
    const requestId = ++threadRequestRef.current;
    try {
      // Load full session with messages
      const sessionData = await agentApi.getSession(threadId);

      // Something newer superseded this call while the fetch was in flight
      // (another selectThread, or startNewThread) — that later call already
      // reflects what the user wants; applying this stale response now would
      // silently revert it.
      if (threadRequestRef.current !== requestId) return false;

      const thread: ConversationThread = {
        id: sessionData.session.session_id,
        title: sessionData.session.title || 'Untitled conversation',
        createdAt: new Date(sessionData.session.created_at),
        updatedAt: new Date(sessionData.session.updated_at),
        messages: sessionData.messages.map(convertAPIMessage),
        pinnedEntities: [], // TODO: load from session context
        definitionId: sessionData.session.definition_id || undefined,
        agentName: sessionData.session.agent_name || undefined,
      };

      setState(prev => ({
        ...prev,
        currentThread: thread,
        selectedAgentId: sessionData.session.definition_id || prev.selectedAgentId,
        activeTab: 'chat',
      }));
      return true;
    } catch (e) {
      console.error('Failed to load session:', e);
      return false;
    }
  }, []);

  const startNewThread = useCallback(() => {
    threadRequestRef.current += 1;
    setState(prev => ({
      ...prev,
      currentThread: null,
      activeTab: 'chat',
    }));
  }, []);

  const renameThread = useCallback(async (threadId: string, title: string) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    // Optimistic: update the rail + open thread immediately, then persist.
    setState(prev => ({
      ...prev,
      threads: prev.threads.map(t => (t.id === threadId ? { ...t, title: trimmed } : t)),
      currentThread:
        prev.currentThread?.id === threadId
          ? { ...prev.currentThread, title: trimmed }
          : prev.currentThread,
    }));
    try {
      await agentApi.renameSession(threadId, trimmed);
    } catch (e) {
      console.error('Failed to rename conversation:', e);
    }
  }, []);

  const deleteThread = useCallback(async (threadId: string) => {
    try {
      await agentApi.deleteSession(threadId);
    } catch (e) {
      console.error('Failed to delete conversation:', e);
      return;
    }
    setState(prev => ({
      ...prev,
      threads: prev.threads.filter(t => t.id !== threadId),
      currentThread: prev.currentThread?.id === threadId ? null : prev.currentThread,
    }));
  }, []);

  const approveAction = useCallback(async (messageId: string, actionId: string) => {
    void messageId;
    void actionId;
    setState(prev => ({ ...prev, error: 'Action approvals are handled by Agent Runs.' }));
  }, []);

  const rejectAction = useCallback(async (messageId: string, actionId: string) => {
    void messageId;
    void actionId;
    setState(prev => ({ ...prev, error: 'Action approvals are handled by Agent Runs.' }));
  }, []);

  const setAgentFocus = useCallback((focus: AgentUIState['agentFocus']) => {
    setState(prev => ({ ...prev, agentFocus: focus }));
  }, []);

  const clearAgentFocus = useCallback(() => {
    setState(prev => ({ ...prev, agentFocus: null }));
  }, []);

  // Suggestions for the start screen: the selected agent's own suggestions when
  // it defines any, otherwise sensible cross-agent defaults (5-6 chips).
  const getSuggestions = useCallback(() => {
    if (agentSuggestions.length > 0) {
      return agentSuggestions.map((s, i) => ({ id: `agent-${i}`, label: s.label, prompt: s.prompt }));
    }
    return [
      { id: 'workflows', label: 'What workflows do we have?', prompt: 'What workflows do we have?' },
      { id: 'board', label: 'Show the pipeline board', prompt: 'Show me the pipeline board' },
      { id: 'dashboard', label: 'Show the dashboard', prompt: 'Show me the dashboard' },
      { id: 'count', label: 'How many candidates?', prompt: 'How many candidates do we have right now?' },
      { id: 'stale', label: 'Find stale applications', prompt: 'Which applications have been stuck in the same stage for too long?' },
      { id: 'sla', label: 'SLA risks', prompt: 'Are there any applications at risk of breaching their SLA?' },
    ];
  }, [agentSuggestions]);

  const value: AgentContextValue = {
    ...state,
    toggleSidebar,
    openSidebar,
    closeSidebar,
    setActiveTab,
    setSidebarWidth,
    selectAgent,
    sendMessage,
    pinEntity,
    unpinEntity,
    clearPinnedEntities,
    selectThread,
    startNewThread,
    loadSessions,
    renameThread,
    deleteThread,
    approveAction,
    rejectAction,
    setAgentFocus,
    clearAgentFocus,
    getSuggestions,
  };

  return (
    <AgentContext.Provider value={value}>
      {children}
    </AgentContext.Provider>
  );
}

export function useAgent() {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgent must be used within an AgentProvider');
  }
  return context;
}
