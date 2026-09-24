/**
 * DashboardTimeFilter
 *
 * Global dashboard time control. Emits a filter fragment the dashboard merges
 * into every widget's query: a preset (`{ time_range }`) or a custom range
 * (`{ date_from, date_to }`). Empty object = all time.
 */
import { format, parse } from 'date-fns';
import { type DateRange } from 'react-day-picker';
import { cn } from '../../lib/utils';
import { DatePickerWithRange } from '../../components/ui/range-picker';
import { Button } from '@/components/ui/button';

export type TimeFilterValue = Record<string, string>;

const PRESETS: { value: string; label: string }[] = [
  { value: '', label: 'All time' },
  { value: 'today', label: 'Today' },
  { value: 'this_week', label: 'This week' },
  { value: 'this_month', label: 'This month' },
  { value: 'last_7d', label: 'Last 7d' },
  { value: 'last_30d', label: 'Last 30d' },
  { value: 'last_90d', label: 'Last 90d' },
  { value: 'last_180d', label: 'Last 180d' },
];

export interface DashboardTimeFilterProps {
  value: TimeFilterValue;
  onChange: (v: TimeFilterValue) => void;
}

export default function DashboardTimeFilter({ value, onChange }: DashboardTimeFilterProps) {
  const isCustom = 'date_from' in value || 'date_to' in value;
  const activePreset = isCustom ? null : (value.time_range ?? '');

  // Map between the ISO-string fragment and react-day-picker's DateRange.
  const toDate = (s?: string) => (s ? parse(s, 'yyyy-MM-dd', new Date()) : undefined);
  const range: DateRange | undefined =
    value.date_from || value.date_to
      ? { from: toDate(value.date_from), to: toDate(value.date_to) }
      : undefined;
  const onRangeChange = (next: DateRange | undefined) => {
    if (!next?.from) {
      onChange({});
      return;
    }
    onChange({
      date_from: format(next.from, 'yyyy-MM-dd'),
      ...(next.to ? { date_to: format(next.to, 'yyyy-MM-dd') } : {}),
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-2 w-full justify-between p-2">
      <DatePickerWithRange value={range} onChange={onRangeChange} placeholder="Custom range" />
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => {
          const active = activePreset === p.value;
          return (
            <Button
              key={p.value || 'all'}
              type="button"
              onClick={() => onChange(p.value ? { time_range: p.value } : {})}
              className={cn(
                'rounded-full border px-3 py-1 text-sm',
                active
                  ? 'border-cobalt bg-cobalt/10 font-medium text-cobalt'
                  : 'border-border text-muted-foreground hover:bg-muted',
              )}
            >
              {p.label}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
