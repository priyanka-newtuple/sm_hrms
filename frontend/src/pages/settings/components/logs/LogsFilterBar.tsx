import type { DateRange } from 'react-day-picker';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { DatePickerWithRange } from '@/components/ui/range-picker';
import type { User } from '@/core/types';
import PersonFilter from './PersonFilter';

type Props = {
  users: User[];
  range: DateRange | undefined;
  userId: string | null;
  onRangeChange: (range: DateRange | undefined) => void;
  onPersonChange: (userId: string | null) => void;
};

/** Date range and person filters for the Logs page. Both optional. */
export function LogsFilterBar({ users, range, userId, onRangeChange, onPersonChange }: Props) {
  const hasFilters = Boolean(range || userId);

  return (
    // h-9 on both controls — the range picker and person picker differ by default.
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">Date range</Label>
        <DatePickerWithRange
          value={range}
          onChange={onRangeChange}
          placeholder="Any time"
          className="h-9 w-56"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label className="text-xs">Person</Label>
        <PersonFilter users={users} value={userId} onChange={onPersonChange} />
      </div>
      {hasFilters && (
        <Button
          variant="ghost"
          className="h-9"
          onClick={() => {
            onRangeChange(undefined);
            onPersonChange(null);
          }}
        >
          Clear filters
        </Button>
      )}
    </div>
  );
}

export default LogsFilterBar;
