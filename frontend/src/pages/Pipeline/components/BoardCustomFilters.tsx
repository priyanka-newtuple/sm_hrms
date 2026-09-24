import { ListFilter } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { FilterBarItem } from '@/skins';

interface BoardCustomFiltersProps {
  available: FilterBarItem[];
  selectedKeys: Set<string>;
  onToggle: (key: string) => void;
}

export default function BoardCustomFilters({
  available,
  selectedKeys,
  onToggle,
}: BoardCustomFiltersProps) {
  if (!available.length) return null;

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="md"
            rounded="lg"
            icon={<ListFilter />}
            aria-label="Customize board filters"
          >
            Filters{selectedKeys.size ? ` (${selectedKeys.size})` : ''}
          </Button>
        }
      />
      <PopoverContent align="end" className="w-72">
        <PopoverHeader>
          <PopoverTitle>Customize filters</PopoverTitle>
          <p className="text-xs text-muted-foreground">
            Choose fields to show in the board toolbar.
          </p>
        </PopoverHeader>
        <div className="max-h-72 space-y-1 overflow-y-auto py-1">
          {available.map((filter) => (
            <label
              key={filter.key}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-muted"
            >
              <Checkbox
                checked={selectedKeys.has(filter.key)}
                onCheckedChange={() => onToggle(filter.key)}
                aria-label={`Show ${filter.label} filter`}
              />
              <span className="truncate">{filter.label}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
