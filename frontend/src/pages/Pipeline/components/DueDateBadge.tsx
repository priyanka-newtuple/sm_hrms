import { CalendarClock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { parseDueDate } from '../utils/dueDate';

export default function DueDateBadge({ value }: { value?: string | null }) {
  const due = parseDueDate(value);
  if (!due) return null;
  const today = new Date();
  const days = Math.ceil((due.getTime() - new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) / 86_400_000);
  const label = days < 0 ? `${Math.abs(days)}d overdue` : days === 0 ? 'Due today' : `${days}d left`;
  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold',
      days < 0 ? 'border-rose/20 bg-rose/10 text-rose' : days <= 2 ? 'border-destructive/30 bg-destructive-subtle text-destructive' : days <= 7 ? 'border-amber/20 bg-amber/10 text-amber' : 'border-emerald/20 bg-emerald/10 text-emerald',
    )}>
      <CalendarClock className="h-3 w-3" /> {label}
    </span>
  );
}
