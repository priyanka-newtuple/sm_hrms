import { MAX_PRIORITY } from "@/lib/roles-data"

interface PriorityBarProps {
  priority: number
  color: string
  maxPriority?: number
}

export function PriorityBar({ priority, color, maxPriority = MAX_PRIORITY }: PriorityBarProps) {
  const percentage = (priority / maxPriority) * 100

  return (
    <div className="flex items-center gap-[10px]">
      <div className="flex-1 max-w-[96px] h-[5px] rounded-[3px] bg-muted overflow-hidden">
        <div
          className="h-full rounded-[3px]"
          style={{
            width: `${percentage}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <span className="text-[13px] font-medium text-foreground tabular-nums min-w-[24px] text-right">
        {priority}
      </span>
    </div>
  )
}
