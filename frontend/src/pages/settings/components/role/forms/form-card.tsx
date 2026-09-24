import type { ColumnDef } from "@tanstack/react-table"

import {
  VISIBILITY_MODES,
  type FieldPermission,
  type VisibilityMode,
} from "@/lib/entity-data"
import type { FormSchema, FormField } from "@/core/types"
import { DataTable } from "@/core/components/DataTable"
import { ContentIcon } from "../shared/icons"
import { ColumnHeaderLabel } from "../shared/column-header"
import { VISIBILITY_ICONS, VISIBILITY_ORDER } from "./visibility"
import { FieldNameCell, VisibilityCell, EditableCell } from "./field-row"

// Skip UI-only / read-only field kinds — they aren't permissionable.
const isPermissionableField = (f: FormField) => f.type !== "section" && f.type !== "reference"

interface FormCardProps {
  form: FormSchema
  term: string
  color: string
  disabled?: boolean
  fpOf: (field: string) => FieldPermission
  onSetFieldVisibility: (field: string, mode: VisibilityMode) => void
  onToggleFieldEdit: (field: string) => void
  onSetFormVisibility: (fields: Array<{ id: string }>, mode: VisibilityMode) => void
}

export function FormCard({
  form,
  term,
  color,
  disabled = false,
  fpOf,
  onSetFieldVisibility,
  onToggleFieldEdit,
  onSetFormVisibility,
}: FormCardProps) {
  const permFields = (form.schema?.fields || []).filter(isPermissionableField)
  const shownFields = permFields.filter(
    (fld) =>
      !term ||
      fld.label.toLowerCase().includes(term) ||
      fld.id.toLowerCase().includes(term) ||
      fld.type.toLowerCase().includes(term)
  )
  if (!shownFields.length) return null

  const columns: ColumnDef<FormField, unknown>[] = [
    {
      id: "field",
      header: "Field",
      accessorFn: (fld) => fld.label,
      cell: ({ row }) => <FieldNameCell field={row.original} />,
    },
    {
      id: "visibility",
      header: () => <ColumnHeaderLabel>Value visibility</ColumnHeaderLabel>,
      cell: ({ row }) => (
        <VisibilityCell
          fp={fpOf(row.original.id)}
          disabled={disabled}
          onSetVisibility={(mode) => onSetFieldVisibility(row.original.id, mode)}
        />
      ),
      meta: { width: "280px" },
    },
    {
      id: "editable",
      header: () => <ColumnHeaderLabel>Editable</ColumnHeaderLabel>,
      cell: ({ row }) => (
        <EditableCell
          fp={fpOf(row.original.id)}
          color={color}
          disabled={disabled}
          onToggleEdit={() => onToggleFieldEdit(row.original.id)}
        />
      ),
      meta: { width: "96px" },
    },
  ]

  return (
    <div className="border border-border rounded-[14px] overflow-hidden">
      {/* Form header */}
      <div className="flex items-center gap-3 py-[13px] px-4 bg-muted border-b border-border">
        <span className="flex text-muted-foreground">
          <ContentIcon width={17} height={17} />
        </span>
        <div className="flex-1">
          <div className="text-[13.5px] font-bold">{form.name}</div>
          <div className="text-[11.5px] text-muted-foreground">{permFields.length} fields</div>
        </div>
        <div className="flex gap-[6px]">
          {VISIBILITY_ORDER.map((m) => {
            const v = VISIBILITY_MODES[m]
            const Icon = VISIBILITY_ICONS[v.icon]
            return (
              <button
                key={m}
                onClick={() => onSetFormVisibility(permFields, m)}
                disabled={disabled}
                className="text-[11.5px] font-semibold py-[5px] px-[9px] rounded-[7px] border border-border bg-card text-foreground cursor-pointer transition-all hover:border-foreground inline-flex items-center gap-[5px] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span style={{ color: v.tone }} className="flex">
                  {Icon && <Icon width={13} height={13} />}
                </span>
                {v.label}
              </button>
            )
          })}
        </div>
      </div>

      <DataTable
        label={`${form.name} fields`}
        data={shownFields}
        columns={columns}
        getRowId={(fld) => fld.id}
        enableSorting={false}
        framed={false}
      />
    </div>
  )
}
