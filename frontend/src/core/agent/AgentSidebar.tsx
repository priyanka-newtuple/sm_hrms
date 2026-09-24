import { useState, useRef, useEffect, type CSSProperties } from 'react';
import {
  X,
  MessageSquare,
  History,
  Send,
  Plus,
  ChevronRight,
  Briefcase,
  User,
  FileText,
  Loader2,
} from 'lucide-react';
import { useAgent, type PinnedEntity } from './AgentContext';
import AgentDropdown from './AgentDropdown';
import ChatMessage, { ThinkingIndicator } from './ChatMessage';
import { Button } from '@/components/ui/button';

// Entity type icon mapping
const EntityIcon = ({ type }: { type: PinnedEntity['type'] }) => {
  switch (type) {
    case 'Job':
      return <Briefcase className="w-3 h-3" />;
    case 'Candidate':
      return <User className="w-3 h-3" />;
    case 'Application':
      return <FileText className="w-3 h-3" />;
  }
};

/** Agent selector for the sidebar — uses shared AgentDropdown. */
const AgentSelector = () => <AgentDropdown variant="bar" />;

// Context Header - shows pinned entities
function ContextHeader() {
  const { pinnedEntities, unpinEntity, clearPinnedEntities } = useAgent();

  if (pinnedEntities.length === 0) return null;

  return (
    <div className="px-4 py-3 border-b border-border/50 bg-gradient-to-r from-cobalt/5 to-cyan/5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
          Context
        </span>
        {pinnedEntities.length > 1 && (
          <Button
            variant="ghost"
            onClick={clearPinnedEntities}
            className="text-[10px] text-muted-foreground hover:text-muted-foreground"
          >
            Clear all
          </Button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {pinnedEntities.map((entity) => (
          <div
            key={entity.id}
            className="inline-flex items-center gap-1.5 px-2 py-1 bg-card rounded-lg border border-border text-xs group"
          >
            <EntityIcon type={entity.type} />
            <span className="text-foreground">{entity.label}</span>
            <Button
              variant="ghost"
              onClick={() => unpinEntity(entity.id)}
              className="text-muted-foreground/60 hover:text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <X className="w-3 h-3" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

// History Tab Content
function HistoryTab() {
  const { threads, selectThread, startNewThread, currentThread, isLoadingSessions } = useAgent();

  const formatDate = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="flex-1 min-w-0 overflow-y-auto">
      {/* New chat button */}
      <div className="p-4 border-b border-border/50">
        <Button variant="primary"
          onClick={startNewThread}
          className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-cobalt text-primary-foreground rounded-xl font-medium hover:bg-cobalt-dark transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Conversation
        </Button>
      </div>

      {/* Loading state */}
      {isLoadingSessions ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-cobalt animate-spin" />
        </div>
      ) : threads.length === 0 ? (
        <div className="p-6 text-center text-muted-foreground text-sm">
          No conversations yet
        </div>
      ) : (
        <div className="divide-y divide-border">
          {threads.map((thread) => (
            <Button variant="ghost"
              key={thread.id}
              onClick={() => selectThread(thread.id)}
              className={`
                h-auto min-h-14 w-full items-start justify-start px-4 py-3 text-left whitespace-normal hover:bg-muted/50 transition-colors
                ${currentThread?.id === thread.id ? 'bg-cobalt/5' : ''}
              `}
            >
              <div className="flex min-w-0 items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {thread.title}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {thread.agentName && (
                      <span className="text-cobalt">{thread.agentName} · </span>
                    )}
                    {thread.messages.length || '?'} messages
                  </p>
                </div>
                <div className="flex flex-col items-end">
                  <span className="text-[10px] text-muted-foreground">
                    {formatDate(thread.updatedAt)}
                  </span>
                  <ChevronRight className="w-4 h-4 text-muted-foreground/60 mt-1" />
                </div>
              </div>
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

// Quick Start Chips
function QuickStartChips() {
  const { sendMessage, getSuggestions, isThinking } = useAgent();
  const suggestions = getSuggestions();

  return (
    <div className="p-4 border-t border-border/50 bg-muted/50">
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
        Quick Start
      </p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((chip) => (
          <Button variant="primary"
            key={chip.id}
            onClick={() => sendMessage(chip.prompt)}
            disabled={isThinking}
            className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-card border border-border rounded-full hover:border-cobalt hover:text-cobalt transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {chip.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

// Chat Tab Content
function ChatTab() {
  const {
    currentThread,
    isThinking,
    sendMessage,
    approveAction,
    rejectAction,
    error,
    isLoadingDefinitions,
    agentDefinitions,
  } = useAgent();

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentThread?.messages, isThinking]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [inputValue]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isThinking) return;

    const message = inputValue.trim();
    setInputValue('');
    await sendMessage(message);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const hasMessages = currentThread && currentThread.messages.length > 0;
  const isReady = !isLoadingDefinitions && agentDefinitions.length > 0;

  return (
    <>
      {/* Messages area */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {!hasMessages ? (
          // Empty state with contextual welcome
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="w-16 h-16 bg-gradient-to-br from-cobalt/10 to-cyan/10 rounded-2xl flex items-center justify-center mb-4">
              <MessageSquare className="w-8 h-8 text-cobalt" />
            </div>
            <h3 className="text-lg font-semibold text-foreground mb-2">
              How can I help?
            </h3>
            <p className="text-sm text-muted-foreground max-w-[240px]">
              I can help you screen candidates, find stale applications, or execute bulk actions.
            </p>
          </div>
        ) : (
          <div className="min-w-0 p-4">
            {currentThread.messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onApprove={approveAction}
                onReject={rejectAction}
              />
            ))}
            {isThinking && <ThinkingIndicator />}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Error display */}
      {error && (
        <div className="px-4 py-2 bg-destructive-subtle border-t border-destructive/30">
          <p className="text-xs text-destructive break-words [overflow-wrap:anywhere]">{error}</p>
        </div>
      )}

      {/* Quick start (only show when no messages) */}
      {!hasMessages && <QuickStartChips />}

      {/* Input area */}
      <div className="min-w-0 p-4 border-t border-border/50">
        <form onSubmit={handleSubmit} className="relative">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isReady ? "Ask me anything..." : "Loading..."}
            disabled={!isReady || isThinking}
            rows={1}
            className="w-full px-4 py-3 pr-12 bg-card border border-border rounded-xl resize-none focus:outline-none focus:border-cobalt focus:ring-1 focus:ring-cobalt text-sm placeholder:text-muted-foreground disabled:bg-muted/50 disabled:cursor-not-allowed break-words [overflow-wrap:anywhere]"
          />
          <Button variant="primary"
            type="submit"
            disabled={!inputValue.trim() || isThinking || !isReady}
            className={`
              absolute right-2 bottom-2 p-2 rounded-lg transition-colors
              ${inputValue.trim() && !isThinking && isReady
                ? 'bg-cobalt text-primary-foreground hover:bg-cobalt-dark'
                : 'bg-muted text-muted-foreground'
              }
            `}
          >
            {isThinking ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </form>
        <p className="text-[10px] text-muted-foreground text-center mt-2">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </>
  );
}

// Main Sidebar Component
export default function AgentSidebar() {
  const { isOpen, closeSidebar, activeTab, setActiveTab, sidebarWidth, setSidebarWidth } = useAgent();
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    if (!isResizing) return;

    const handlePointerMove = (event: PointerEvent) => {
      setSidebarWidth(window.innerWidth - event.clientX);
    };
    const handlePointerUp = () => {
      setIsResizing(false);
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isResizing, setSidebarWidth]);

  return (
    <>
      {/* Sidebar Panel */}
      <aside
        style={{ '--agent-sidebar-width': `${sidebarWidth}px` } as CSSProperties}
        className={`
          fixed inset-y-0 right-0 z-50
          w-full sm:w-[var(--agent-sidebar-width)] max-w-full
          bg-card border-l border-border/50
          shadow-2xl shadow-gray-200/50
          flex flex-col min-w-0
          transition-transform duration-300 ease-out
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
      >
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize agent pane"
          aria-valuenow={sidebarWidth}
          onPointerDown={(event) => {
            event.preventDefault();
            setIsResizing(true);
          }}
          className={`
            hidden sm:block absolute left-0 top-0 h-full w-3 -translate-x-1/2
            cursor-col-resize touch-none
            after:absolute after:left-1/2 after:top-0 after:h-full after:w-px after:-translate-x-1/2
            after:bg-transparent hover:after:bg-cobalt/40
            ${isResizing ? 'after:bg-cobalt/60' : ''}
          `}
        />

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
          {/* Tab buttons */}
          <div className="flex gap-1 p-1 bg-muted rounded-lg">
            <Button variant="primary"
              onClick={() => setActiveTab('chat')}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
                ${activeTab === 'chat'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
                }
              `}
            >
              <MessageSquare className="w-4 h-4" />
              Chat
            </Button>
            <Button variant="primary"
              onClick={() => setActiveTab('history')}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
                ${activeTab === 'history'
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
                }
              `}
            >
              <History className="w-4 h-4" />
              History
            </Button>
          </div>

          {/* Close button */}
          <Button variant="ghost"
            onClick={closeSidebar}
            className="p-2 text-muted-foreground hover:text-muted-foreground hover:bg-muted rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Agent Selector (only in chat tab) */}
        {activeTab === 'chat' && (
          <div className="px-4 py-2 border-b border-border/50">
            <AgentSelector />
          </div>
        )}

        {/* Context Header (shared across tabs) */}
        <ContextHeader />

        {/* Tab Content */}
        {activeTab === 'chat' ? <ChatTab /> : <HistoryTab />}
      </aside>
    </>
  );
}
