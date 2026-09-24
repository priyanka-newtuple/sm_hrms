import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export interface McpConnectorFilterOption {
  id: string;
  label: string;
  count: number;
}

interface McpConnectorFilterProps {
  options: McpConnectorFilterOption[];
  totalCount: number;
  value: string;
  onChange: (value: string) => void;
}

export const ALL_APPS_VALUE = 'all';

/**
 * "Filter by app" dropdown for a tool list spanning multiple connected apps.
 * A dropdown rather than a pill row scales to any number of connectors without
 * wrapping or crowding the header as more apps get connected.
 */
export default function McpConnectorFilter({ options, totalCount, value, onChange }: McpConnectorFilterProps) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-48">
        <SelectValue placeholder="All apps" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_APPS_VALUE}>All apps ({totalCount})</SelectItem>
        {options.map(option => (
          <SelectItem key={option.id} value={option.id}>
            {option.label} ({option.count})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
