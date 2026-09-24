import { hexToRgba, type Role } from "@/lib/roles-data"
import { ShieldIcon, BackIcon, MoreIcon } from "../shared/icons"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu"

interface RoleDetailHeaderProps {
  role: Role
  onBack: () => void
  onDelete?: () => void
  isNew?: boolean
  canWrite?: boolean
}

export function RoleDetailHeader({
  role,
  onBack,
  onDelete,
  isNew,
  canWrite = true,
}: RoleDetailHeaderProps) {
  const color = role.color ?? '#4F46E5'

  return (
    <>
      {/* Back button */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-[6px] text-[13px] text-muted-foreground mb-[18px] transition-colors hover:text-foreground bg-transparent border-none cursor-pointer p-0"
      >
        <BackIcon width={16} height={16} />
        Back to Roles
      </button>

      {/* Title row */}
      <div className="flex items-start justify-between mb-[22px]">
        <div className="flex gap-3.5">
          <div
            className="w-[46px] h-[46px] rounded-xl flex items-center justify-center flex-shrink-0"
            style={{
              backgroundColor: hexToRgba(color, 0.12),
              color,
            }}
          >
            <ShieldIcon width={23} height={23} sw={1.8} />
          </div>
          <div>
            <div className="text-[11.5px] font-semibold tracking-[0.08em] text-muted-foreground uppercase mb-[3px]">
              {isNew ? "New Role" : "Edit Role"}
            </div>
            <h1 className="m-0 text-[22px] font-bold tracking-[-0.01em] text-foreground">
              {role.display_name}
            </h1>
          </div>
        </div>

        {!isNew && onDelete && (
          <DropdownMenu>
            <DropdownMenuTrigger
              title="More"
              disabled={!canWrite}
              className="w-[38px] h-[38px] rounded-[9px] border border-border bg-card flex items-center justify-center text-muted-foreground cursor-pointer transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              <MoreIcon width={18} height={18} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem variant="destructive" onClick={onDelete} disabled={!canWrite}>
                Delete role
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </>
  )
}
