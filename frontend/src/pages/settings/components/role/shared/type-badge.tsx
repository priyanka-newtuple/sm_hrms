import { hexToRgba } from "@/lib/roles-data"
import { LockIcon } from "./icons"

interface TypeBadgeProps {
  isSystem: boolean
  color: string
}

export function TypeBadge({ isSystem, color }: TypeBadgeProps) {
  if (isSystem) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-muted px-[7px] py-[2.5px] text-[11.5px] font-medium text-muted-foreground">
        <LockIcon width={11} height={11} />
        System
      </span>
    )
  }
  return (
    <span
      className="rounded-md px-[7px] py-[2.5px] text-[11.5px] font-medium"
      style={{
        color,
        backgroundColor: hexToRgba(color, 0.1),
      }}
    >
      Custom
    </span>
  )
}
