import { LayoutGrid, ListChecks, Search } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { FilterBarItem } from '@/skins';
import PipelineTerminalToggle from './PipelineTerminalToggle';
import BoardCustomFilters from './BoardCustomFilters';
import BoardFilterBar from './BoardFilterBar';
import AssigneeAvatarFilter from './PipelineListView/AssigneeAvatarFilter';

interface AssigneeOption {
  id: string;
  name: string;
}

interface PipelineBoardToolbarProps {
  view: 'list' | 'kanban';
  onViewChange: (view: 'list' | 'kanban') => void;
  search: string;
  onSearchChange: (search: string) => void;
  /** Omitted entirely when the workflow has no terminal states. */
  terminalToggle?: {
    hidden: boolean;
    label: string;
    onToggle: (hidden: boolean) => void | Promise<void>;
  };
  /**
   * The "Filters" bubble (picks which entity fields get their own filter
   * control) plus the normal select/daterange/assignee controls it adds to
   * the toolbar once picked — same `BoardCustomFilters` + `BoardFilterBar`
   * pairing the main /pipeline page uses. Omitted entirely when the workflow
   * has no filterable fields.
   */
  customFilters?: {
    available: FilterBarItem[];
    selectedKeys: Set<string>;
    onToggleAvailable: (key: string) => void;
    values: Record<string, string>;
    onChange: (key: string, value: string) => void;
  };
  /** Omitted entirely when the assignee filter is disabled org- or skin-wide. */
  assigneeFilter?: {
    options: AssigneeOption[];
    hasUnassigned: boolean;
    selectedIds: string[];
    onToggle: (id: string) => void;
    onClear: () => void;
    currentUserId?: string;
  };
}

/** Compact Board/Table + search + "Hide <terminal>" toolbar for embedding a
 *  pipeline board somewhere with no page-level chrome of its own (the agent
 *  canvas) — a lightweight stand-in for the /pipeline page's own header/tabs. */
export default function PipelineBoardToolbar({
  view,
  onViewChange,
  search,
  onSearchChange,
  terminalToggle,
  customFilters,
  assigneeFilter,
}: PipelineBoardToolbarProps) {
  const selectedCustomFilters = customFilters?.available.filter((f) => customFilters.selectedKeys.has(f.key)) ?? [];

  return (
    <div className="mb-3 flex shrink-0 flex-wrap items-center gap-2">
      <Tabs value={view} onValueChange={(v) => onViewChange(v === 'kanban' ? 'kanban' : 'list')}>
        <TabsList>
          <TabsTrigger value="kanban">
            <LayoutGrid className="mr-1.5 h-4 w-4" />
            Board
          </TabsTrigger>
          <TabsTrigger value="list">
            <ListChecks className="mr-1.5 h-4 w-4" />
            Table
          </TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="relative min-w-[220px] flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          placeholder="Search this workflow…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="h-9 w-full rounded-xl border border-border bg-muted/50 pl-8 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-cobalt/40 focus:outline-none focus:ring-2 focus:ring-cobalt/10"
        />
      </div>
      {assigneeFilter && (
        <AssigneeAvatarFilter
          options={assigneeFilter.options}
          hasUnassigned={assigneeFilter.hasUnassigned}
          selectedIds={assigneeFilter.selectedIds}
          onToggle={assigneeFilter.onToggle}
          onClear={assigneeFilter.onClear}
          currentUserId={assigneeFilter.currentUserId}
        />
      )}
      {selectedCustomFilters.length > 0 && customFilters && (
        <BoardFilterBar
          filters={selectedCustomFilters}
          values={customFilters.values}
          onChange={customFilters.onChange}
        />
      )}
      {customFilters && (
        <BoardCustomFilters
          available={customFilters.available}
          selectedKeys={customFilters.selectedKeys}
          onToggle={customFilters.onToggleAvailable}
        />
      )}
      {terminalToggle && (
        <PipelineTerminalToggle
          hidden={terminalToggle.hidden}
          label={terminalToggle.label}
          onToggle={terminalToggle.onToggle}
        />
      )}
    </div>
  );
}
