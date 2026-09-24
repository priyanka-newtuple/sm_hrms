import { type Role, hexToRgba, MAX_PRIORITY } from "@/lib/roles-data"
import Input, { Textarea } from "@/core/components/Input"
import { FormField, Divider } from "../shared/form-field"
import ColorSwatchPicker from "@/core/components/ColorSwatchPicker"

interface DisplayTabProps {
  role: Role
  setRole: (role: Role) => void
  disabled?: boolean
}

export function DisplayTab({ role, setRole, disabled = false }: DisplayTabProps) {
  return (
    <div className="max-w-[680px]">
      <div className="mb-[22px]">
        <Input
          label="Display name"
          required
          value={role.display_name}
          onChange={(e) => setRole({ ...role, display_name: e.target.value })}
          disabled={disabled}
        />
      </div>

      <div className="mb-[22px]">
        <Input
          label="System name"
          required
          helperText="Lowercase letters, numbers, and underscores only. No spaces."
          value={role.name}
          onChange={(e) => setRole({ ...role, name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') })}
          disabled={disabled}
          className="font-mono"
        />
      </div>

      <div className="mb-[22px]">
        <Textarea
          label="Description"
          helperText="Shown on the roles list and member tooltips."
          value={role.description || ""}
          onChange={(e) => setRole({ ...role, description: e.target.value || null })}
          rows={3}
          disabled={disabled}
        />
      </div>

      <Divider />

      <FormField label="Role color" required hint="Identifies the role across lists, members, and audit logs.">
        <div className="mt-1">
          <ColorSwatchPicker
            value={role.color}
            onChange={(hex) => setRole({ ...role, color: hex })}
            disabled={disabled}
          />
        </div>
      </FormField>

      <Divider />

      <FormField
        label="Priority"
        hint="Higher priority wins when a member has multiple roles. Range 0–100."
      >
        <div className="flex items-center gap-[18px] mt-[6px]">
          <input
            type="range"
            min="0"
            max={MAX_PRIORITY}
            value={role.priority}
            onChange={(e) => setRole({ ...role, priority: +e.target.value })}
            disabled={disabled}
            className="flex-1 disabled:cursor-not-allowed disabled:opacity-60"
            style={{ accentColor: role.color }}
          />
          <div className="w-[58px] text-center font-bold text-[15px] tabular-nums border border-border rounded-lg py-[7px]">
            {role.priority}
          </div>
        </div>
      </FormField>

      <Divider />

      <div>
        <div className="text-[13.5px] font-semibold mb-[10px]">Preview</div>
        <div className="flex items-center gap-3 border border-border rounded-xl p-[14px_16px] bg-muted">
          <span
            className="w-[11px] h-[11px] rounded"
            style={{
              backgroundColor: role.color,
              boxShadow: `0 0 0 3px ${hexToRgba(role.color, 0.15)}`,
            }}
          />
          <span
            className="font-semibold text-sm"
            style={{ color: role.color }}
          >
            {role.display_name || "Untitled role"}
          </span>
          <span
            className="text-[11.5px] font-semibold rounded-md px-2 py-[2.5px]"
            style={{
              color: role.color,
              backgroundColor: hexToRgba(role.color, 0.1),
            }}
          >
            Custom
          </span>
        </div>
      </div>
    </div>
  )
}
