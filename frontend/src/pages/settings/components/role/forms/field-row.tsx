import {
  VISIBILITY_MODES,
  getVisibilityMode,
  type FieldPermission,
  type VisibilityMode,
} from "@/lib/entity-data"
import type { FormField } from "@/core/types"
import { VISIBILITY_ICONS, VISIBILITY_ORDER } from "./visibility"
import { ColorToggle } from "../shared/color-toggle"

export function FieldNameCell({ field }: { field: FormField }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">{field.label}</span>
        {field.required && (
          <span className="text-[8.5px] font-bold tracking-[0.03em] rounded-[4px] py-[0.5px] px-[4px] leading-none text-warning bg-warning-subtle">
            REQUIRED
          </span>
        )}
      </div>
      <div className="text-[11.5px] text-muted-foreground">
        {field.type} · <span className="font-mono">{field.id}</span>
      </div>
    </div>
  )
}

export function VisibilityCell({
  fp,
  disabled = false,
  onSetVisibility,
}: {
  fp: FieldPermission
  disabled?: boolean
  onSetVisibility: (mode: VisibilityMode) => void
}) {
  const mode = getVisibilityMode(fp)
  return (
    <div className="flex justify-center">
      <div className="inline-flex bg-muted rounded-[9px] p-[3px] gap-[2px]">
        {VISIBILITY_ORDER.map((m) => {
          const sel = mode === m
          const v = VISIBILITY_MODES[m]
          const Icon = VISIBILITY_ICONS[v.icon]
          return (
            <button
              key={m}
              onClick={() => onSetVisibility(m)}
              title={v.label}
              disabled={disabled}
              className="inline-flex items-center gap-[5px] py-[5px] px-[10px] rounded-[6px] border-none cursor-pointer text-xs font-semibold transition-shadow disabled:cursor-not-allowed disabled:opacity-50"
              style={{
                backgroundColor: sel ? "var(--card)" : "transparent",
                color: sel ? v.tone : "var(--muted-foreground)",
                boxShadow: sel ? "0 1px 2px rgba(0,0,0,.08)" : "none",
              }}
            >
              {Icon && <Icon width={14} height={14} />}
              {v.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function EditableCell({
  fp,
  color,
  disabled = false,
  onToggleEdit,
}: {
  fp: FieldPermission
  color: string
  disabled?: boolean
  onToggleEdit: () => void
}) {
  return (
    <div className="flex justify-center">
      <ColorToggle checked={fp.edit} onCheckedChange={onToggleEdit} color={color} disabled={disabled || !fp.view || fp.mask} />
    </div>
  )
}
