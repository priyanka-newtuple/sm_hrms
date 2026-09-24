import { useState, type ReactNode } from 'react';
import { ArrowRight, ChevronDown, Flag, Loader2, Lock } from 'lucide-react';
import { toast } from 'sonner';
import { getApiErrorMessage } from '@/core/services/api/client';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAvailableTransitions } from '@/shared/hooks';
import { resolveStateLabel, resolveTransitionLabel } from '@/shared/utils/labels';
import { cn } from '@/lib/utils';
import type { AvailableTransition } from '@/core/types';

interface TransitionActionsProps {
  entityId: string;
  workflowId?: string;
  /** Page-batched previews supplied by list summaries. Detail views omit this and fetch normally. */
  availableTransitions?: AvailableTransition[];
  /** `inline` = a "move to" list of next states (detail panel);
   *  `menu` = a compact "move to" control for list rows. */
  variant: 'inline' | 'menu';
  onExecuted?: () => void;
  /** Changing this re-fetches available transitions (e.g. when entity data updates). */
  refreshKey?: unknown;
  /** menu variant: render a "Terminal" flag when the entity has no transitions. */
  showTerminal?: boolean;
}

const isAllowed = (t: AvailableTransition) => t.allowed !== false;
const blockedReason = (t: AvailableTransition) =>
  t.blocked_reasons?.join('; ') || 'Not available yet';
const inlineMenuWidth = 'w-[min(17.5rem,calc(100vw-1.5rem))]';
const listMenuWidth = 'w-[min(15rem,calc(100vw-1.5rem))]';

/** Destination-led descriptor. A generic "Move to <state>" label (auto-generated,
 *  often with a raw un-humanized state name) is redundant with the destination we
 *  already show — collapse it to just the humanized destination. Meaningful authored
 *  labels ("Reject", "Advance") are kept, with a `→ dest` hint alongside.
 *  ponytail: prefix heuristic; if authors ever write real copy starting "Move to …",
 *  gate on an explicit "auto-labeled" flag instead. */
function describe(t: AvailableTransition) {
  const dest = resolveStateLabel(t.to_state);
  const raw = resolveTransitionLabel(t);
  const isGenericMove = /^\s*move\s+to\b/i.test(raw);
  const action = isGenericMove ? dest : raw;
  return { dest, action, showDest: !isGenericMove && action !== dest };
}

export default function TransitionActions({
  entityId,
  workflowId,
  availableTransitions,
  variant,
  onExecuted,
  refreshKey,
  showTerminal,
}: TransitionActionsProps) {
  const { available, loading, error, execute, refetch } = useAvailableTransitions(
    entityId,
    refreshKey,
    availableTransitions,
    workflowId,
  );
  const [executing, setExecuting] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const busy = executing !== null;

  const run = async (t: AvailableTransition) => {
    const { dest, action } = describe(t);
    setExecuting(t.trigger);
    try {
      await execute(t.trigger);
      toast.success(t.to_state ? `Moved to ${dest}` : action);
      setOpen(false);
      onExecuted?.();
      void refetch();
    } catch (e) {
      const is403 = (e as { status?: number }).status === 403;
      toast.error('Transition failed', {
        description: is403
          ? `You don't have permission to run "${action}".`
          : getApiErrorMessage(e, `"${action}" could not be completed.`),
      });
      void refetch();
    } finally {
      setExecuting(null);
    }
  };

  const menuRow = (t: AvailableTransition) => {
    const allowed = isAllowed(t);
    const d = describe(t);
    return (
      <DropdownMenuItem
        key={t.trigger}
        disabled={busy || !allowed}
        closeOnClick={false}
        onClick={(e) => {
          e.stopPropagation();
          if (allowed) void run(t);
        }}
        className={cn(
          'items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors',
          allowed
            ? 'focus:bg-primary/10 focus:text-foreground'
            : 'focus:bg-muted/50 focus:text-muted-foreground',
        )}
      >
        <span
          className={cn(
            'inline-flex h-6 w-6 flex-none items-center justify-center rounded-md border',
            allowed
              ? 'border-border/80 bg-background text-primary shadow-crisp group-focus/dropdown-menu-item:border-primary/25 group-focus/dropdown-menu-item:bg-primary/10'
              : 'border-border/70 bg-muted/50 text-muted-foreground',
          )}
        >
          {executing === t.trigger ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : allowed ? (
            <ArrowRight className="h-3.5 w-3.5 text-primary group-focus/dropdown-menu-item:text-primary" />
          ) : (
            <Lock className="h-3 w-3" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium leading-4 text-foreground group-focus/dropdown-menu-item:text-foreground">
            {d.dest}
          </span>
          {!allowed && (
            <span className="block text-[11px] leading-4 text-muted-foreground group-focus/dropdown-menu-item:text-muted-foreground">
              {blockedReason(t)}
            </span>
          )}
        </span>
      </DropdownMenuItem>
    );
  };

  if (loading) return <Loader2 className="ml-auto h-4 w-4 animate-spin text-muted-foreground" />;
  if (error) return <span className="ml-auto text-xs text-destructive">Failed to load actions</span>;

  if (available.length === 0) {
    if (variant === 'menu' && showTerminal) {
      return (
        <span className="inline-flex h-7 items-center gap-1.5 rounded-md border border-primary/15 bg-primary/5 px-2 text-[11px] font-medium text-primary">
          <Flag className="h-3 w-3" />
          Terminal
        </span>
      );
    }
    return null;
  }

  // Allowed transitions first, guard-blocked after.
  const sorted = [...available].sort((a, b) => Number(isAllowed(b)) - Number(isAllowed(a)));

  // Shared popover: the caller's trigger over one identical transition list.
  // Keeps the inline (detail) and menu (list row) variants from drifting apart.
  const menuPanel = (trigger: ReactNode, widthClass: string) => (
    <div className="ml-auto inline-flex" onClick={(e) => e.stopPropagation()}>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        {trigger}
        <DropdownMenuContent
          align="end"
          sideOffset={6}
          className={cn(widthClass, 'rounded-lg border border-border/80 bg-card p-1.5 shadow-float')}
        >
          <div className="mb-1 flex items-center justify-between border-b border-border/70 px-2 pb-1.5 pt-0.5">
            <p className="text-[11px] font-medium text-muted-foreground">Move to</p>
            <span className="text-[10px] tabular-nums text-muted-foreground/80">{sorted.length}</span>
          </div>
          {sorted.map((t) => menuRow(t))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );

  // Detail views always use one neutral trigger; choosing a transition only
  // happens from the menu, even when there is a single available option.
  if (variant === 'inline') {
    return menuPanel(
      <DropdownMenuTrigger
        disabled={busy}
        className="inline-flex h-8 min-w-0 items-center gap-1.5 rounded-lg border border-primary/20 bg-primary px-3 text-xs font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:opacity-60 focus:outline-none"
        aria-label="Move to another state"
      >
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <ArrowRight className="h-3.5 w-3.5" />
        )}
        <span className="truncate">Move to</span>
        <ChevronDown className="h-3.5 w-3.5 opacity-80" />
      </DropdownMenuTrigger>,
      inlineMenuWidth,
    );
  }

  // A single compact-list action can execute directly without a menu.
  if (sorted.length === 1) {
    const t = sorted[0];
    const allowed = isAllowed(t);
    const { dest } = describe(t);
    return (
      <button
        type="button"
        title={allowed ? undefined : blockedReason(t)}
        disabled={busy || !allowed}
        onClick={(e) => {
          e.stopPropagation();
          if (allowed) void run(t);
        }}
        className={cn(
          'ml-auto inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-60',
          allowed
            ? 'border-primary/20 bg-primary/5 text-primary hover:bg-primary/10'
            : 'cursor-not-allowed border-border bg-muted/50 text-muted-foreground',
        )}
      >
        {executing === t.trigger ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : allowed ? (
          <ArrowRight className="h-3.5 w-3.5" />
        ) : (
          <Lock className="h-3.5 w-3.5" />
        )}
        <span>{dest}</span>
      </button>
    );
  }

  // 2+ transitions, menu (list row): compact trigger over the shared transition menu.
  return menuPanel(
    <DropdownMenuTrigger
      disabled={busy}
      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-primary/20 bg-primary/5 px-2.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
      aria-label="Move to another state"
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
      <span>Move to</span>
      <span className="rounded bg-primary/10 px-1 text-[10px] tabular-nums leading-4">
        {sorted.length}
      </span>
      <ChevronDown className="h-3.5 w-3.5 opacity-70" />
    </DropdownMenuTrigger>,
    listMenuWidth,
  );
}
