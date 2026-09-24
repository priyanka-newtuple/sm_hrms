import { Clock } from 'lucide-react';
import { cn } from '@/lib/utils';

const DAY_MS = 1000 * 60 * 60 * 24;

interface SlaTagProps {
  slaDate: string;
}

export default function SlaTag({ slaDate }: SlaTagProps) {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(slaDate);
  const dueAt = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]), 23, 59, 59, 999)
    : new Date(slaDate);
  const msLeft = dueAt.getTime() - Date.now();
  const daysLeft = Math.floor(msLeft / DAY_MS);
  const overdue = msLeft < 0;

  const label = overdue
    ? `${Math.abs(daysLeft)}d overdue`
    : daysLeft === 0
      ? 'Due today'
      : `${daysLeft}d left`;

  // ponytail: warning threshold is intentionally shared by SLA and fixed-deadline pills for v1.
  const tone = overdue
    ? 'border-rose/20 bg-rose/10 text-rose'
    : daysLeft <= 2
      ? 'border-amber/20 bg-amber/10 text-amber'
      : 'border-emerald/20 bg-emerald/10 text-emerald';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold',
        tone,
      )}
    >
      <Clock className="h-3 w-3" />
      {label}
    </span>
  );
}
