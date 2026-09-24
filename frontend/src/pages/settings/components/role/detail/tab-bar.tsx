import { cn } from "@/lib/utils"

interface Tab {
  id: string
  label: string
  badge?: number
}

interface TabBarProps {
  tabs: Tab[]
  activeTab: string
  onTabChange: (tabId: string) => void
}

export function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex gap-7 border-b border-border mb-[26px]">
      {tabs.map((tab) => {
        const active = activeTab === tab.id
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative bg-transparent border-none pb-[13px] cursor-pointer text-sm font-semibold transition-colors hover:text-foreground",
              active ? "text-cobalt" : "text-muted-foreground"
            )}
          >
            <span className="inline-flex items-center gap-[7px]">
              {tab.label}
              {tab.badge !== undefined && (
                <span
                  className={cn(
                    "text-[11px] font-bold rounded-full py-[1px] px-[7px] tabular-nums",
                    active
                      ? "text-cobalt bg-cobalt/10"
                      : "text-muted-foreground bg-muted"
                  )}
                >
                  {tab.badge}
                </span>
              )}
            </span>
            {active && (
              <span className="absolute left-0 right-0 -bottom-px h-[2px] bg-cobalt rounded" />
            )}
          </button>
        )
      })}
    </div>
  )
}
