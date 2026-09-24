import { Search } from 'lucide-react';
import { displayEntityType, pluralizeEntityType } from '../helpers';

interface DetailFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  routeEntityType: string;
  filterType: string;
  onFilterTypeChange: (value: string) => void;
  entityTypes: string[];
}

export default function DetailFilters({
  search,
  onSearchChange,
  routeEntityType,
  filterType,
  onFilterTypeChange,
  entityTypes,
}: DetailFiltersProps) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="relative flex-1 max-w-xs">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={
            routeEntityType
              ? `Search ${pluralizeEntityType(displayEntityType(routeEntityType)).toLowerCase()}…`
              : 'Search entities…'
          }
          className="w-full rounded-lg border border-input bg-background py-2 pr-3 pl-9 text-sm text-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
        />
      </div>
      {!routeEntityType && entityTypes.length > 1 && (
        <select
          value={filterType}
          onChange={(e) => onFilterTypeChange(e.target.value)}
          className="rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
        >
          <option value="">All types</option>
          {entityTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
