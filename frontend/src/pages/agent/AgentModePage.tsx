import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SidebarProvider, SidebarInset, SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
import { useAgent } from '@/core/agent';
import { usePermissions } from '@/core/hooks/usePermissions';
import { AccessDenied } from '@/core/components';
import AgentChatPanel from './AgentChatPanel';
import AgentCanvas from './AgentCanvas';
import AgentHistorySidebar from './AgentHistorySidebar';
import { useCanvasItems } from './useAgentCanvas';

const CHAT_PCT_KEY = 'agent-chat-width-pct';
const LAST_SESSION_KEY = 'agent-last-session-id';
const MIN_PCT = 28;
const MAX_PCT = 68;

function readInitialPct(): number {
  if (typeof window === 'undefined') return 42;
  const saved = Number(window.localStorage.getItem(CHAT_PCT_KEY));
  return Number.isFinite(saved) && saved >= MIN_PCT && saved <= MAX_PCT ? saved : 42;
}

/** True on md+ viewports (where the resizable side-by-side split applies). */
function useIsDesktop(): boolean {
  const [desktop, setDesktop] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(min-width: 768px)').matches : true,
  );
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = () => setDesktop(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return desktop;
}

/**
 * Full-screen Agent Mode (STAT-334). ChatGPT/Claude-style 3-pane layout: a
 * collapsible history rail, a center conversation, and a right-hand canvas that
 * slides in when the agent renders a component. Chat/canvas widths are
 * drag-resizable; the history rail auto-collapses when the canvas opens.
 */
function AgentModeInner() {
  const navigate = useNavigate();
  const { currentThread, loadSessions, selectThread } = useAgent();
  const { setOpen } = useSidebar();
  const items = useCanvasItems(currentThread);
  const hasCanvas = items.length > 0;
  const desktop = useIsDesktop();

  // Restore the last-open conversation (and, since the canvas is a pure
  // projection of its messages, whatever workflow board/list it had open) when
  // this page remounts — e.g. after clicking through to a full-page entity
  // detail and coming back. AgentModeLayout mounts its own AgentProvider, so
  // `currentThread` is otherwise lost on every unmount; this is the one thing
  // that survives it. Runs once on mount only — deliberately not re-triggered
  // by `currentThread` changes, so it never fights a thread the user just
  // switched to or a "New conversation" click.
  useEffect(() => {
    const lastSessionId = window.localStorage.getItem(LAST_SESSION_KEY);
    if (!lastSessionId) return;
    void selectThread(lastSessionId).then((ok) => {
      // A superseded restore (the user picked a different thread before this
      // resolved) isn't a failure — only a genuine miss (session deleted/
      // expired, request error) should tell the user their conversation is
      // gone rather than leaving them looking at a silently blank chat.
      if (!ok && window.localStorage.getItem(LAST_SESSION_KEY) === lastSessionId) {
        toast.error("Couldn't restore your last conversation", {
          description: 'It may have been deleted or expired — starting a new one.',
        });
        window.localStorage.removeItem(LAST_SESSION_KEY);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the "last session" pointer in sync — cleared when the user
  // explicitly starts a new conversation (`startNewThread` sets `currentThread`
  // to `null`), so returning to /agent afterwards doesn't resurrect the old one.
  useEffect(() => {
    if (currentThread?.id) window.localStorage.setItem(LAST_SESSION_KEY, currentThread.id);
    else window.localStorage.removeItem(LAST_SESSION_KEY);
  }, [currentThread?.id]);

  const [chatPct, setChatPct] = useState(readInitialPct);
  const [resizing, setResizing] = useState(false);
  const pctRef = useRef(chatPct);
  const draggingRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevHasCanvas = useRef(hasCanvas);

  // Populate the history rail on entry (the docked provider does this lazily on
  // its history tab, which this full-screen page doesn't have).
  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  // Auto-collapse the history rail the first time the canvas opens, so it gets
  // maximum room. The user can reopen it any time (trigger / Cmd-Ctrl+B).
  useEffect(() => {
    if (hasCanvas && !prevHasCanvas.current) setOpen(false);
    prevHasCanvas.current = hasCanvas;
  }, [hasCanvas, setOpen]);

  // Drag-to-resize the chat/canvas split (desktop only).
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      const clamped = Math.min(MAX_PCT, Math.max(MIN_PCT, pct));
      pctRef.current = clamped;
      setChatPct(clamped);
    };
    const onUp = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      setResizing(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.localStorage.setItem(CHAT_PCT_KEY, String(pctRef.current));
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, []);

  const startResize = (e: React.PointerEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    setResizing(true);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
  };

  const splitActive = hasCanvas && desktop;

  return (
    <>
      <AgentHistorySidebar />
      <SidebarInset className="min-h-0">
        <div className="flex h-svh min-h-0 flex-col bg-background">
          {/* Top bar */}
          <header className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <SidebarTrigger className="text-muted-foreground" />
              <span className="h-2 w-2 rounded-full bg-cobalt" />
              <h1 className="text-sm font-semibold tracking-tight text-foreground">Agent Mode</h1>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              aria-label="Exit agent mode"
              className="text-muted-foreground"
            >
              <X className="mr-1.5 h-4 w-4" />
              Exit
            </Button>
          </header>

          {/* Chat + canvas. Chat is centered until the canvas opens, then it
              becomes a resizable left column and the canvas slides in. */}
          <div ref={containerRef} className="flex min-h-0 flex-1 flex-col md:flex-row">
            <div
              className={[
                splitActive
                  ? 'min-h-0 shrink-0 border-b border-border md:border-b-0 md:border-r'
                  : 'min-h-0 w-full flex-1',
                resizing ? '' : 'transition-[width] duration-500 ease-out',
              ].join(' ')}
              style={splitActive ? { width: `${chatPct}%` } : undefined}
            >
              <AgentChatPanel />
            </div>

            {splitActive && (
              <div
                role="separator"
                aria-orientation="vertical"
                onPointerDown={startResize}
                className="group hidden w-1.5 shrink-0 cursor-col-resize items-stretch md:flex"
              >
                <div className="mx-auto w-px bg-border transition-colors group-hover:bg-cobalt/50" />
              </div>
            )}

            {hasCanvas && (
              <div className="min-h-0 flex-1 animate-in fade-in slide-in-from-right-4 duration-500 ease-out">
                <AgentCanvas />
              </div>
            )}
          </div>
        </div>
      </SidebarInset>
    </>
  );
}

export default function AgentModePage() {
  // The /agent route is only login-gated (ProtectedRoute); enforce the agent
  // permission here too so navigating straight to it is denied for roles without
  // it — mirrors how permission-gated pages (e.g. dashboard) guard themselves.
  // The backend endpoints also require agent:read/agent:write.
  const { hasPermission, loading } = usePermissions();

  if (loading) {
    return (
      <div className="flex h-svh items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!hasPermission('agent:read')) {
    return (
      <div className="flex h-svh items-center justify-center bg-background p-6">
        <AccessDenied message="You don't have permission to use Agent Mode." />
      </div>
    );
  }

  return (
    <SidebarProvider>
      <AgentModeInner />
    </SidebarProvider>
  );
}
