import { VISIBILITY_MODES, type VisibilityMode } from "@/lib/entity-data"
import { VISIBILITY_ICONS } from "./visibility"

export function VisibilityLegend() {
  return (
    <div className="flex items-center gap-4 text-xs text-muted-foreground">
      {(Object.entries(VISIBILITY_MODES) as [VisibilityMode, typeof VISIBILITY_MODES.full][]).map(
        ([k, v]) => {
          const Icon = VISIBILITY_ICONS[v.icon]
          return (
            <span key={k} className="inline-flex items-center gap-[5px]">
              <span style={{ color: v.tone }} className="flex">
                {Icon && <Icon width={14} height={14} />}
              </span>
              {v.label}
            </span>
          )
        }
      )}
    </div>
  )
}
