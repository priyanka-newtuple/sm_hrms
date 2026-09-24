import { useEffect, useMemo, useRef, useState } from 'react';
import { Send, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAgent } from '@/core/agent';
import AgentDropdown from '@/core/agent/AgentDropdown';
import ChatMessage from '@/core/agent/ChatMessage';
import { useWorkflows, type Workflow } from '@/shared/hooks';
import { useCanvasItems } from './useAgentCanvas';
import { deriveFollowUps } from './followUps';

/**
 * Data-driven start-screen chips: built from the org's actual workflows so the
 * suggestions reflect what the user can actually initiate right now (and use
 * real workflow names the agent can resolve). Falls back to the agent's own
 * suggestions when no workflows exist yet.
 */
function buildStartChips(
  workflows: Workflow[],
  fallback: { id: string; label: string; prompt: string }[],
): { id: string; label: string; prompt: string }[] {
  const active = workflows.filter((w) => w.isActive);
  if (active.length === 0) return fallback;

  const chips: { id: string; label: string; prompt: string }[] = [];
  for (const w of active.slice(0, 3)) {
    chips.push({ id: `board-${w.id}`, label: `${w.label} board`, prompt: `Show me the ${w.label} board` });
  }
  const first = active[0];
  chips.push({
    id: `count-${first.id}`,
    label: `Count in ${first.label}`,
    prompt: `How many entities are in the ${first.label} workflow right now?`,
  });
  chips.push({ id: 'dashboard', label: 'Show the dashboard', prompt: 'Show me the dashboard' });
  return chips.slice(0, 6);
}

/** Agent picker for the chat panel header — uses shared AgentDropdown. */
const AgentPicker = () => <AgentDropdown variant="pill" />;

export default function AgentChatPanel() {
  const {
    currentThread,
    isThinking,
    error,
    sendMessage,
    approveAction,
    rejectAction,
    getSuggestions,
  } = useAgent();
  const { workflows } = useWorkflows();
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const messages = currentThread?.messages ?? [];
  const isEmpty = messages.length === 0;
  const canvasItems = useCanvasItems(currentThread);

  const startChips = useMemo(() => buildStartChips(workflows, getSuggestions()), [workflows, getSuggestions]);

  // Contextual follow-ups: only offered once the agent has replied and isn't
  // mid-turn; derived from what's currently on the canvas.
  const lastMessage = messages[messages.length - 1];
  const followUps =
    !isEmpty && !isThinking && lastMessage?.role === 'agent' ? deriveFollowUps(canvasItems) : [];

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length, isThinking]);

  const submit = () => {
    const text = input.trim();
    if (!text || isThinking) return;
    setInput('');
    void sendMessage(text);
  };

  const composer = (
    <div className="rounded-2xl border border-border bg-background p-2 shadow-sm focus-within:ring-2 focus-within:ring-cobalt/25">
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Message the agent…"
        rows={1}
        className="max-h-40 min-h-[24px] w-full resize-none border-0 bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
      />
      {/* Agent picker sits to the right of the input, beside Send (ChatGPT-style). */}
      <div className="flex items-center justify-end gap-2 pt-1">
        <AgentPicker />
        <Button
          variant="primary"
          onClick={submit}
          disabled={!input.trim() || isThinking}
          className="h-9 w-9 shrink-0 rounded-xl p-0"
          aria-label="Send"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );

  // Empty state = a centered ChatGPT-style start screen.
  if (isEmpty) {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex min-h-0 flex-1 items-center justify-center px-4">
          <div className="w-full max-w-xl space-y-6 text-center">
            <div className="flex justify-center">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cobalt/10 text-cobalt">
                <Sparkles className="h-7 w-7" />
              </span>
            </div>
            <div className="space-y-1.5">
              <h2 className="text-2xl font-semibold tracking-tight text-foreground">How can I help?</h2>
              <p className="text-sm text-muted-foreground">
                Ask about your workflows or data - results render live on the canvas.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {startChips.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  onClick={() => void sendMessage(chip.prompt)}
                  disabled={isThinking}
                  className="rounded-full border border-border bg-background px-3.5 py-2 text-xs font-medium text-foreground transition-colors hover:border-cobalt hover:text-cobalt disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="shrink-0 px-4 pb-4">
          <div className="mx-auto max-w-2xl">{composer}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Messages */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto max-w-2xl space-y-1">
          {messages.map((m) => (
            <ChatMessage key={m.id} message={m} onApprove={approveAction} onReject={rejectAction} />
          ))}
          {isThinking && <p className="px-1 py-2 text-xs text-muted-foreground">Thinking…</p>}
        </div>
      </div>

      {error && <div className="shrink-0 px-4 py-1.5 text-xs text-red-500">{error}</div>}

      {/* Follow-up pills + composer */}
      <div className="shrink-0 border-t border-border p-3">
        <div className="mx-auto max-w-2xl space-y-2">
          {followUps.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {followUps.map((chip) => (
                <button
                  key={chip.id}
                  type="button"
                  onClick={() => void sendMessage(chip.prompt)}
                  disabled={isThinking}
                  className="rounded-full border border-border bg-muted/40 px-3 py-1.5 text-xs text-foreground transition-colors hover:border-cobalt hover:text-cobalt disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {chip.label}
                </button>
              ))}
            </div>
          )}
          {composer}
        </div>
      </div>
    </div>
  );
}
