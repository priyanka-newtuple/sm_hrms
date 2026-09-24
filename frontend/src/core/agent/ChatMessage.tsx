import { Terminal, Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ChatMessage as ChatMessageType, ToolExecution, PendingActionUI } from './AgentContext';

// Parse markdown and render with React components
function renderMarkdown(content: string, isUser: boolean): React.ReactNode[] {
  const elements: React.ReactNode[] = [];

  // Combined regex for bold, links, and inline code
  // Matches: **bold**, [text](url), `code`
  const regex = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|`[^`]+`)/g;

  let lastIndex = 0;
  let match;
  let keyIndex = 0;

  while ((match = regex.exec(content)) !== null) {
    // Add text before the match
    if (match.index > lastIndex) {
      elements.push(content.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token.startsWith('**') && token.endsWith('**')) {
      // Bold text
      elements.push(
        <strong key={keyIndex++} className="font-semibold">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('[') && token.includes('](')) {
      // Link: [text](url)
      const linkMatch = token.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        const [, text, url] = linkMatch;
        // Check if it's an internal link (starts with /)
        if (url.startsWith('/')) {
          elements.push(
            <Link
              key={keyIndex++}
              to={url}
              className={`break-words [overflow-wrap:anywhere] underline hover:no-underline ${isUser ? 'text-primary-foreground/90' : 'text-cobalt hover:text-cobalt-dark'}`}
            >
              {text}
            </Link>
          );
        } else {
          elements.push(
            <a
              key={keyIndex++}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className={`break-words [overflow-wrap:anywhere] underline hover:no-underline ${isUser ? 'text-primary-foreground/90' : 'text-cobalt hover:text-cobalt-dark'}`}
            >
              {text}
            </a>
          );
        }
      }
    } else if (token.startsWith('`') && token.endsWith('`')) {
      // Inline code
      elements.push(
        <code
          key={keyIndex++}
          className={`break-words [overflow-wrap:anywhere] px-1 py-0.5 rounded text-xs font-mono ${isUser ? 'bg-card/20' : 'bg-muted text-foreground'}`}
        >
          {token.slice(1, -1)}
        </code>
      );
    }

    lastIndex = match.index + token.length;
  }

  // Add remaining text
  if (lastIndex < content.length) {
    elements.push(content.slice(lastIndex));
  }

  return elements;
}

interface ToolExecutionChipProps {
  execution: ToolExecution;
}

function formatJson(value: unknown): string {
  if (value === undefined || value === null || value === '') return 'No payload';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function getToolStatusLabel(status: ToolExecution['status']): string {
  if (status === 'running') return 'Running';
  if (status === 'success') return 'Success';
  return 'Error';
}

function ToolStatusIcon({ status }: { status: ToolExecution['status'] }) {
  if (status === 'running') return <Loader2 className="h-3.5 w-3.5 animate-spin text-cobalt" />;
  if (status === 'success') return <CheckCircle2 className="h-3.5 w-3.5 text-emerald" />;
  return <XCircle className="h-3.5 w-3.5 text-rose" />;
}

function ToolExecutionDetails({ execution }: ToolExecutionChipProps) {
  const statusLabel = getToolStatusLabel(execution.status);
  const hasDuration = typeof execution.duration_ms === 'number';

  return (
    <details className="group rounded-lg border border-border bg-card">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-muted/50">
        <ToolStatusIcon status={execution.status} />
        <span className="min-w-0 flex-1 truncate font-mono font-medium">{execution.name}</span>
        <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {statusLabel}
        </span>
        {hasDuration && (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {execution.duration_ms}ms
          </span>
        )}
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground group-open:hidden" />
        <ChevronUp className="hidden h-3.5 w-3.5 shrink-0 text-muted-foreground group-open:block" />
      </summary>

      <div className="space-y-3 border-t border-border px-3 py-3">
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Input
          </div>
          <pre className="max-h-48 overflow-y-auto overflow-x-hidden rounded-md border border-border bg-muted/50 p-2 text-[11px] leading-relaxed text-foreground whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {formatJson(execution.input)}
          </pre>
        </div>

        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {execution.status === 'error' ? 'Error / Output' : 'Output'}
          </div>
          <pre className="max-h-56 overflow-y-auto overflow-x-hidden rounded-md border border-border bg-muted/50 p-2 text-[11px] leading-relaxed text-foreground whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {formatJson(execution.output)}
          </pre>
        </div>
      </div>
    </details>
  );
}

interface ToolExecutionsPanelProps {
  executions: ToolExecution[];
}

function ToolExecutionsPanel({ executions }: ToolExecutionsPanelProps) {
  const successful = executions.filter((execution) => execution.status === 'success').length;
  const failed = executions.filter((execution) => execution.status === 'error').length;
  const running = executions.filter((execution) => execution.status === 'running').length;

  return (
    <details className="group mb-3 rounded-xl border border-border bg-muted/70">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-muted/50">
        <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="font-medium">
          Tool call{executions.length === 1 ? '' : 's'}
        </span>
        <span className="rounded-full bg-card px-2 py-0.5 text-[10px] text-muted-foreground ring-1 ring-border">
          {executions.length}
        </span>
        <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">
          {successful > 0 && `${successful} succeeded`}
          {successful > 0 && (failed > 0 || running > 0) && ' · '}
          {failed > 0 && `${failed} failed`}
          {failed > 0 && running > 0 && ' · '}
          {running > 0 && `${running} running`}
        </span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground group-open:hidden" />
        <ChevronUp className="hidden h-3.5 w-3.5 shrink-0 text-muted-foreground group-open:block" />
      </summary>

      <div className="space-y-2 border-t border-border px-2 py-2">
        {executions.map((execution, index) => (
          <ToolExecutionDetails
            key={`${execution.name}-${index}`}
            execution={execution}
          />
        ))}
      </div>
    </details>
  );
}

interface PendingActionCardProps {
  action: PendingActionUI;
}

function PendingActionCard({ action }: PendingActionCardProps) {
  if (action.status === 'approved') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-emerald/10 rounded-lg border border-emerald/20">
        <CheckCircle2 className="w-4 h-4 text-emerald flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium text-emerald">Executed: </span>
          <span className="text-sm text-emerald/80">{action.description}</span>
        </div>
      </div>
    );
  }

  if (action.status === 'rejected') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-muted rounded-lg">
        <XCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-sm text-muted-foreground">Cancelled: </span>
          <span className="text-sm text-muted-foreground">{action.description}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="px-3 py-2 bg-warning-subtle rounded-lg border border-warning/30">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono bg-warning-subtle px-1.5 py-0.5 rounded text-warning">
              {action.type}
            </span>
          </div>
          <p className="text-sm text-foreground break-words [overflow-wrap:anywhere]">{action.description}</p>
        </div>
      </div>
      <p className="mt-2 text-xs text-warning">
        Approval is handled by the Agent Runs workflow.
      </p>
    </div>
  );
}

interface ChatMessageProps {
  message: ChatMessageType;
  onApprove: (messageId: string, actionId: string) => void;
  onReject: (messageId: string, actionId: string) => void;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <div className="flex justify-center my-4">
        <div className="px-3 py-1.5 bg-muted rounded-full text-xs text-muted-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex min-w-0 ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`
          min-w-0 max-w-[85%] overflow-hidden rounded-2xl px-4 py-3 break-words [overflow-wrap:anywhere]
          ${isUser
            ? 'bg-cobalt text-primary-foreground rounded-br-md'
            : 'bg-card border border-border shadow-sm rounded-bl-md'
          }
        `}
      >
        {/* Tool executions (for agent messages) */}
        {!isUser && message.toolExecutions && message.toolExecutions.length > 0 && (
          <ToolExecutionsPanel executions={message.toolExecutions} />
        )}

        {/* Message content */}
        <div
          className={`
            text-sm leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere]
            ${isUser ? 'text-primary-foreground' : 'text-foreground'}
          `}
        >
          {renderMarkdown(message.content, isUser)}
        </div>

        {/* Pending actions */}
        {!isUser && message.pendingActions && message.pendingActions.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border space-y-2">
            <div className="text-xs text-muted-foreground mb-2">
              Proposed action{message.pendingActions.length > 1 ? 's' : ''}:
            </div>
            {message.pendingActions.map((action) => (
              <PendingActionCard
                key={action.action_id}
                action={action}
              />
            ))}
          </div>
        )}

        {/* Timestamp */}
        <div
          className={`
            text-[10px] mt-2
            ${isUser ? 'text-primary-foreground/60' : 'text-muted-foreground'}
          `}
        >
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}

// Thinking indicator component
export function ThinkingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="flex items-center gap-2 px-4 py-3 bg-card border border-border shadow-sm rounded-2xl rounded-bl-md">
        <div className="flex gap-1">
          <div className="w-2 h-2 bg-cobalt/60 rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 bg-cobalt/60 rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 bg-cobalt/60 rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
        </div>
        <span className="text-xs text-muted-foreground">Thinking...</span>
      </div>
    </div>
  );
}
