import { Button } from "@/core/components";
import { ShieldIcon, RefreshIcon, PlusIcon } from "../shared/icons"

interface RolesHeaderProps {
  totalRoles: number
  totalMembers: number
  onRefresh: () => void
  onCreate: () => void
  canWrite?: boolean
}

export function RolesHeader({
  totalRoles,
  totalMembers,
  onRefresh,
  onCreate,
  canWrite = true,
}: RolesHeaderProps) {
  return (
    <div className="flex items-start justify-between mb-[22px]">
      <div className="flex gap-3.5">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <ShieldIcon width={22} height={22} sw={1.8} />
        </div>
        <div>
          <h1 className="m-0 mt-[2px] mb-1 whitespace-nowrap text-[21px] font-semibold tracking-[-0.01em] text-foreground">
            Roles &amp; Permissions
          </h1>
          <div className="text-[13.5px] text-muted-foreground">
            {totalRoles} roles · {totalMembers} members assigned
          </div>
        </div>
      </div>
      <div className="flex gap-2.5">
        <Button
          variant="secondary"
          size="md"
          onClick={onRefresh}
          className="inline-flex items-center gap-[7px] cursor-pointer transition-colors"
        >
          <RefreshIcon width={15} height={15} />
          Refresh
        </Button>
        <Button
          variant="primary"
          size="md"
          onClick={onCreate}
          disabled={!canWrite}
          className="inline-flex items-center gap-[7px] cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <PlusIcon width={16} height={16} />
          New Role
        </Button>
      </div>
    </div>
  )
}
