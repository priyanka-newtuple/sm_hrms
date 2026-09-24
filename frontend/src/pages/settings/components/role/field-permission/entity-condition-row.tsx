import {
  MAX_ENTITY_READ_FILTER_CONDITIONS,
  isEntityFilterComplete,
  isMembershipOperator,
  type EntityCondition,
  type EntityFilter,
} from "@/lib/entity-data"
import {
  ENTITY_CONDITION_OPERATORS,
  type EntityConditionOperator,
  type EntityType,
  type FormField,
} from "@/core/types"
import { ColorToggle } from "../shared/color-toggle"

const OPERATOR_LABELS: Record<EntityConditionOperator, string> = {
  "==": "Equals",
  "!=": "Not equals",
  in: "Is one of",
  not_in: "Is not one of",
}

interface EntityConditionRowProps {
  entity: EntityType
  fields: FormField[]
  condition: EntityFilter | undefined
  entityViewable: boolean
  disabled: boolean
  color?: string | null
  onToggle: () => void
  onChange: (filter: EntityFilter) => void
}

const inputClass = "border border-border rounded-lg py-2 px-[10px] text-[13.5px] text-foreground bg-card outline-none focus:border-cobalt focus:ring-[3px] focus:ring-cobalt/20"

interface ConditionFieldsProps {
  row: EntityCondition
  index: number
  fields: FormField[]
  disabled: boolean
  removable: boolean
  onChange: (patch: Partial<EntityCondition>) => void
  onRemove: () => void
}

function ConditionFields({ row, index, fields, disabled, removable, onChange, onRemove }: ConditionFieldsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {index > 0 && (
        <select
          aria-label={`Connector before condition ${index + 1}`}
          value={row.conjunction}
          disabled={disabled}
          onChange={(e) => onChange({ conjunction: e.target.value as "AND" | "OR" })}
          className={inputClass}
        >
          <option value="AND">AND</option>
          <option value="OR">OR</option>
        </select>
      )}
      <select
        aria-label={`Field for condition ${index + 1}`}
        value={row.entity_field}
        disabled={disabled}
        onChange={(e) => onChange({ entity_field: e.target.value })}
        className={inputClass}
      >
        <option value="" disabled>Select a field...</option>
        {fields.map((field) => <option key={field.id} value={field.id}>{field.label}</option>)}
      </select>
      <select
        aria-label={`Operator for condition ${index + 1}`}
        value={row.operator}
        disabled={disabled}
        onChange={(e) => onChange({ operator: e.target.value as EntityConditionOperator })}
        className={inputClass}
      >
        {ENTITY_CONDITION_OPERATORS.map((operator) => (
          <option key={operator} value={operator}>{OPERATOR_LABELS[operator]}</option>
        ))}
      </select>
      <input
        aria-label={`Value for condition ${index + 1}`}
        value={row.condition_value}
        disabled={disabled}
        maxLength={256}
        onChange={(e) => onChange({ condition_value: e.target.value })}
        placeholder={isMembershipOperator(row.operator) ? "store-A, store-B" : "Enter a value"}
        className={`flex-1 min-w-[160px] ${inputClass}`}
      />
      {removable && (
        <button
          type="button"
          aria-label={`Remove condition ${index + 1}`}
          disabled={disabled}
          className="text-sm text-muted-foreground hover:text-destructive disabled:opacity-50"
          onClick={onRemove}
        >
          Remove
        </button>
      )}
    </div>
  )
}

/** One entity's read filter. AND binds before OR; roles still combine with OR. */
export function EntityConditionRow({
  entity, fields, condition, entityViewable, disabled, color, onToggle, onChange,
}: EntityConditionRowProps) {
  const hasFields = fields.length > 0

  const update = (index: number, patch: Partial<EntityCondition>) => {
    if (!condition) return
    onChange({
      conditions: condition.conditions.map((row, i) => i === index ? { ...row, ...patch } : row),
    })
  }

  const add = (conjunction: "AND" | "OR") => {
    if (!condition) return
    onChange({
      conditions: [...condition.conditions, {
        conjunction,
        entity_field: "",
        operator: "==",
        value_source: "LITERAL",
        condition_value: "",
      }],
    })
  }

  const remove = (index: number) => {
    if (!condition) return
    onChange({
      conditions: condition.conditions
        .filter((_, i) => i !== index)
        .map((row, i) => i === 0 ? { ...row, conjunction: "AND" } : row),
    })
  }

  return (
    <div className="border border-border rounded-[14px] overflow-hidden bg-card">
      <div className="flex items-center justify-between py-[10px] px-[18px] bg-muted border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold truncate">{entity.display_name || entity.name}</span>
          {!entityViewable && (
            <span className="shrink-0 text-[11px] font-medium text-warning bg-warning-subtle rounded-full px-2 py-[2px]">
              View not granted
            </span>
          )}
        </div>
        <div className="shrink-0 flex items-center gap-2">
          <span className="text-[12.5px] text-muted-foreground">{condition ? "Filtered" : "Full access"}</span>
          <ColorToggle
            checked={!!condition}
            onCheckedChange={onToggle}
            color={color ?? undefined}
            disabled={disabled || !entityViewable || !hasFields}
          />
        </div>
      </div>
      {!hasFields && (
        <div className="py-[14px] px-[18px] text-[13px] text-muted-foreground">
          No fields defined on this entity type — nothing to filter by.
        </div>
      )}
      {hasFields && !entityViewable && (
        <div className="py-[14px] px-[18px] text-[13px] text-warning">
          Grant View for this entity type in the Entity Access tab first.
        </div>
      )}
      {hasFields && entityViewable && condition && (
        <div className="space-y-3 py-[14px] px-[18px]">
          {condition.conditions.map((row, index) => (
            <ConditionFields
              key={index}
              row={row}
              index={index}
              fields={fields}
              disabled={disabled}
              removable={condition.conditions.length > 1}
              onChange={(patch) => update(index, patch)}
              onRemove={() => remove(index)}
            />
          ))}
          <div className="flex gap-3">
            {(["AND", "OR"] as const).map((conjunction) => (
              <button
                key={conjunction}
                type="button"
                disabled={disabled || condition.conditions.length >= MAX_ENTITY_READ_FILTER_CONDITIONS}
                onClick={() => add(conjunction)}
                className="text-sm font-medium text-cobalt disabled:opacity-50"
              >
                + {conjunction} condition
              </button>
            ))}
          </div>
          {condition.conditions.some((row) => isMembershipOperator(row.operator)) && (
            <p className="text-xs text-muted-foreground">
              Separate values with commas. Text values are case-sensitive; spaces around each entered value are ignored.
              For multi-select fields, “Is one of” matches any listed selection; “Is not one of” excludes every listed selection.
              Missing and empty fields do not match either operator.
            </p>
          )}
          {condition.conditions.length > 1 && (
            <p className="text-xs text-muted-foreground">
              AND is evaluated before OR: A AND B OR C means (A AND B) OR C.
            </p>
          )}
          {condition.conditions.some((row) => !isMembershipOperator(row.operator) && row.condition_value.includes(",")) ? (
            <p className="text-xs text-destructive">
              Commas are not allowed with &ldquo;Equals&rdquo; or &ldquo;Not equals&rdquo;. Use &ldquo;Is one of&rdquo; or &ldquo;Is not one of&rdquo; to match multiple values.
            </p>
          ) : !isEntityFilterComplete(condition) ? (
            <p className="text-xs text-destructive">
              Every condition needs a field and at least one non-empty value, or remove it.
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}
