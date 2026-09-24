import { hexToRgba } from "@/lib/roles-data"
import { simpleName } from "@/lib/entity-data"
import type { EntityType } from "@/core/types"

interface EntityTabsProps {
  entityTypes: EntityType[]
  activeEntity: string
  entityPerms: Set<string>
  color: string
  onSelect: (typeKey: string) => void
}

export function EntityTabs({ entityTypes, activeEntity, entityPerms, color, onSelect }: EntityTabsProps) {
  return (
    <div className="flex gap-2 mb-[18px] flex-wrap">
      {entityTypes.map((e) => {
        const typeKey = e.name
        const active = activeEntity === typeKey
        const viewable = entityPerms.has(`${typeKey}:view`)

        return (
          <button
            key={e.id}
            onClick={() => onSelect(typeKey)}
            className="inline-flex items-center gap-2 py-2 px-[14px] rounded-[10px] border text-[13.5px] font-semibold cursor-pointer transition-colors"
            style={{
              borderColor: active ? "transparent" : "var(--border)",
              backgroundColor: active ? hexToRgba(color, 0.1) : "var(--card)",
              color: active ? color : "var(--foreground)",
            }}
          >
            {e.display_name || simpleName(e.name)}
            {!viewable && (
              <span className="text-[10.5px] font-semibold text-muted-foreground bg-muted rounded-[5px] py-[1px] px-[5px]">
                no view
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
