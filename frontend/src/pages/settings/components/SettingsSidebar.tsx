import { useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

export interface SettingsTabConfig {
  id: string;
  label: string;
  icon: LucideIcon;
  count?: number | string;
  permission?: string;
  superAdminOnly?: boolean;
}

export interface SettingsTabGroup<T extends string = string> {
  label: string;
  tabs: Array<Omit<SettingsTabConfig, 'id'> & { id: T }>;
}

interface SettingsSidebarProps<T extends string = string> {
  groups: SettingsTabGroup<T>[];
  activeTab: T | null;
  onTabChange: (id: T) => void;
}

export default function SettingsSidebar<T extends string>({
  groups,
  activeTab,
  onTabChange,
}: SettingsSidebarProps<T>) {
  const [search, setSearch] = useState('');

  const filteredGroups = search.trim()
    ? groups
        .map(g => ({
          ...g,
          tabs: g.tabs.filter(t => t.label.toLowerCase().includes(search.toLowerCase())),
        }))
        .filter(g => g.tabs.length > 0)
    : groups;

  return (
    <div className="flex h-full w-64 flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
      {/* Search */}
      <div className="px-3 pt-4 pb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-sidebar-foreground/40 pointer-events-none" />
          <input
            type="text"
            placeholder="Find a setting..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full h-9 rounded-lg border border-sidebar-border bg-background/50 pl-9 pr-3 text-sm text-sidebar-foreground placeholder:text-sidebar-foreground/40 focus:outline-none focus:ring-2 focus:ring-sidebar-ring"
          />
        </div>
      </div>

      {/* Groups */}
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {filteredGroups.map(group => (
          <div key={group.label} className="mb-2">
            <div className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.15em] text-sidebar-foreground/50">
              {group.label}
            </div>
            <div>
              {group.tabs.map(tab => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => onTabChange(tab.id)}
                    className={cn(
                      'w-full flex items-center gap-2.5 rounded-md px-2 py-2 text-sm text-left transition-colors',
                      isActive
                        ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
                        : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
                    )}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="flex-1 truncate">{tab.label}</span>
                    {tab.count !== undefined && (
                      <span className="text-xs text-sidebar-foreground/45 tabular-nums">{tab.count}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        {filteredGroups.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-sidebar-foreground/50">
            No settings match &ldquo;{search}&rdquo;
          </p>
        )}
      </div>
    </div>
  );
}
