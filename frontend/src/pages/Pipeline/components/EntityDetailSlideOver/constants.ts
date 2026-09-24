import {
  Archive,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Hourglass,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  ShieldX,
  UserCheck,
  XCircle,
  Zap,
} from 'lucide-react';

// ── Timeline event kinds ──────────────────────────────────────────────────────

export type TimelineEventKind =
  | 'transition_succeeded'
  | 'transition_blocked'
  | 'transition_conflict'
  | 'task_executed'
  | 'entity_created'
  | 'entity_updated'
  | 'assignee_changed'
  | 'entity_archived'
  | 'entity_restored'
  | 'action_started'
  | 'action_completed'
  /** The action ran and reached a verdict, but deliberately changed nothing —
   *  declining to assign a suspended user, say. Distinct from `action_failed`
   *  on purpose: one needs an engineer, the other needs a business decision. */
  | 'action_refused'
  | 'action_failed'
  | 'action_retry_scheduled'
  | 'action_waiting_external'
  | 'action_chain_skipped'
  | 'action_chain_stopped';

// ── Chip visual config ────────────────────────────────────────────────────────

export interface ChipConfig {
  chipBg: string;
  iconColor: string;
  Icon: React.ComponentType<{ className?: string }>;
}

export const CHIP_CONFIG: Record<TimelineEventKind, ChipConfig> = {
  transition_succeeded: { chipBg: 'bg-cobalt/10',  iconColor: 'text-cobalt',           Icon: ArrowRight    },
  transition_blocked:   { chipBg: 'bg-amber/10',   iconColor: 'text-amber',            Icon: ShieldX       },
  transition_conflict:  { chipBg: 'bg-rose/10',    iconColor: 'text-rose',             Icon: AlertTriangle },
  task_executed:        { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: Zap           },
  entity_created:       { chipBg: 'bg-emerald/10', iconColor: 'text-emerald',          Icon: Plus          },
  entity_updated:       { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: Pencil        },
  assignee_changed:     { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: UserCheck     },
  entity_archived:      { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: Archive       },
  entity_restored:      { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: RotateCcw     },
  action_started:          { chipBg: 'bg-cobalt/10',  iconColor: 'text-cobalt',           Icon: Play         },
  action_completed:        { chipBg: 'bg-emerald/10', iconColor: 'text-emerald',          Icon: CheckCircle2 },
  action_refused:          { chipBg: 'bg-amber/10',   iconColor: 'text-amber',            Icon: AlertTriangle},
  action_failed:           { chipBg: 'bg-rose/10',    iconColor: 'text-rose',             Icon: XCircle      },
  action_retry_scheduled:  { chipBg: 'bg-amber/10',   iconColor: 'text-amber',            Icon: Clock        },
  action_waiting_external: { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: Hourglass    },
  action_chain_skipped:    { chipBg: 'bg-muted',      iconColor: 'text-muted-foreground', Icon: ShieldX      },
  action_chain_stopped:    { chipBg: 'bg-amber/10',   iconColor: 'text-amber',            Icon: ShieldX      },
};
