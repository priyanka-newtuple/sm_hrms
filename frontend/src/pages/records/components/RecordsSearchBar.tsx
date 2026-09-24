import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';

interface RecordsSearchBarProps {
  value: string;
  onChange: (value: string) => void;
  total: number;
}

export default function RecordsSearchBar({ value, onChange, total }: RecordsSearchBarProps) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <div className="relative flex-1 max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search entities…"
          className="h-10 pl-9 pr-12 rounded-lg"
        />
        <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          ⌘K
        </kbd>
      </div>
      <div className="ml-auto text-xs text-muted-foreground">
        {total} {total === 1 ? 'entity' : 'entities'}
      </div>
    </div>
  );
}
