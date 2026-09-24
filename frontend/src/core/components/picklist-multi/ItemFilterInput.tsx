/** Narrows step 3's item grid. Matches on the item's value or its label. */

import { Search } from 'lucide-react';

type ItemFilterInputProps = {
  value: string;
  itemCount: number;
  onChange: (value: string) => void;
};

export default function ItemFilterInput({ value, itemCount, onChange }: ItemFilterInputProps) {
  return (
    <div className="relative mt-2.5 max-w-[280px]">
      <Search
        size={15}
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={`Filter ${itemCount} items`}
        className="w-full rounded-lg border border-border bg-card py-2 pl-8 pr-2.5 text-sm text-foreground outline-none focus:border-cobalt focus:ring-2 focus:ring-cobalt"
      />
    </div>
  );
}
