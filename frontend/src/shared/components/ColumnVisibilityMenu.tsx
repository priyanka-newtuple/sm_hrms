import { Columns3, type LucideIcon } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuCheckboxItem,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/** A field this menu can toggle. Structurally satisfied by the pipeline's
 *  `ColumnField` and by the records list's own column descriptors, so neither
 *  page has to depend on the other's types. */
export interface ColumnVisibilityField {
  field: string;
  label: string;
  /** `'standard'` splits the field into the structural group; anything else
   *  (including omitted) reads as a custom, entity-type-specific field. */
  group?: string;
}

const STANDARD_GROUP = 'standard';

/** Field id → why it can't be toggled on right now. Presence of a key marks
 *  that field disabled; the value is shown in a tooltip on hover so the
 *  reason is never a silent dead end (a selection cap, an unsupported field
 *  type, etc. — callers can key any reason they like off this same map). An
 *  already-selected field always stays toggleable regardless of this map,
 *  so a capped picker can still be used to remove a choice. */
export type FieldDisabledReasons = Partial<Record<string, string>>;

interface ColumnVisibilityMenuProps {
  /** all selectable data fields */
  fields: ColumnVisibilityField[];
  /** ids currently shown */
  selectedIds: string[];
  /** number of columns currently visible, for the trigger badge */
  visibleCount: number;
  onToggle: (field: string) => void;
  /** Overrides the trigger label ("Columns" by default). */
  triggerLabel?: string;
  /** Overrides the trigger icon (Columns3 by default). */
  triggerIcon?: LucideIcon;
  /** Overrides the trigger badge's denominator; defaults to `fields.length`.
   *  Used by callers with a fixed selection cap (e.g. "up to 3 fields") that
   *  don't want the badge reading against the full candidate list. */
  maxCount?: number;
  disabledReasons?: FieldDisabledReasons;
  /** Extra classes merged onto the trigger button, appended after (so they
   *  can override) the default sizing/border/background. */
  triggerClassName?: string;
}

interface FieldToggleProps {
  selectedIds: string[];
  onToggle: (field: string) => void;
  disabledReasons?: FieldDisabledReasons;
}

/** A single toggleable field row, shared by the grouped and ungrouped layouts.
 *  A disabled row is wrapped in a Tooltip on a plain (non-disabled) span, not
 *  on the checkbox item itself — the item's own `data-disabled:pointer-events-none`
 *  means it never receives a hover event to trigger a tooltip attached
 *  directly to it. */
function FieldCheckboxItem({ field, selectedIds, onToggle, disabledReasons }: FieldToggleProps & { field: ColumnVisibilityField }) {
  const checked = selectedIds.includes(field.field);
  const reason = checked ? undefined : disabledReasons?.[field.field];
  const item = (
    <DropdownMenuCheckboxItem
      checked={checked}
      disabled={Boolean(reason)}
      onCheckedChange={() => onToggle(field.field)}
      className="focus:bg-primary/10 focus:text-foreground"
    >
      {field.label}
    </DropdownMenuCheckboxItem>
  );
  if (!reason) return item;
  return (
    <Tooltip>
      <TooltipTrigger render={<span className="block" />}>{item}</TooltipTrigger>
      <TooltipContent side="left">{reason}</TooltipContent>
    </Tooltip>
  );
}

/** A titled section of toggleable fields (e.g. "Standard fields"). */
function FieldGroupSection({
  title,
  fields,
  selectedIds,
  onToggle,
  disabledReasons,
}: FieldToggleProps & { title: string; fields: ColumnVisibilityField[] }) {
  return (
    <DropdownMenuGroup>
      <DropdownMenuLabel className="px-2 pb-1 pt-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
        {title}
      </DropdownMenuLabel>
      {fields.map((f) => (
        <FieldCheckboxItem key={f.field} field={f} selectedIds={selectedIds} onToggle={onToggle} disabledReasons={disabledReasons} />
      ))}
    </DropdownMenuGroup>
  );
}

/** The dropdown's trigger button: icon, label, and a "N/M" count badge. Split
 *  out so the default export stays under the file's function-size limit. */
function MenuTriggerButton({
  label,
  Icon,
  visibleCount,
  totalCount,
  className,
}: {
  label: string;
  Icon: LucideIcon;
  visibleCount: number;
  totalCount: number;
  className?: string;
}) {
  return (
    <DropdownMenuTrigger
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-md border border-input bg-background px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary focus:outline-none focus:ring-2 focus:ring-primary/10',
        className,
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
      <span className="rounded bg-muted px-1 text-[10px] tabular-nums text-muted-foreground">
        {visibleCount}/{totalCount}
      </span>
    </DropdownMenuTrigger>
  );
}

/** Dropdown letting the user choose which data-field columns are visible.
 *  Fields are split into two groups — standard (structural, e.g. Status/
 *  Owner) and custom (entity-type form fields) — so a flat list mixing rarely
 *  -hidden structural columns with optional custom data doesn't read as one
 *  undifferentiated pile. Falls back to a single ungrouped list when only one
 *  group is present, so callers with no fixed columns see no visual change. */
export default function ColumnVisibilityMenu({
  fields,
  selectedIds,
  visibleCount,
  onToggle,
  triggerLabel = 'Columns',
  triggerIcon = Columns3,
  maxCount,
  disabledReasons,
  triggerClassName,
}: ColumnVisibilityMenuProps) {
  const standardFields = fields.filter((f) => f.group === STANDARD_GROUP);
  const customFields = fields.filter((f) => f.group !== STANDARD_GROUP);
  const isGrouped = standardFields.length > 0 && customFields.length > 0;

  return (
    <DropdownMenu>
      <MenuTriggerButton
        label={triggerLabel}
        Icon={triggerIcon}
        visibleCount={visibleCount}
        totalCount={maxCount ?? fields.length}
        className={triggerClassName}
      />
      <DropdownMenuContent
        align="end"
        sideOffset={5}
        className="w-52 rounded-lg border border-border/80 bg-card p-1.5 shadow-float"
      >
        <div className="mb-1 border-b border-border/70 px-2 pb-1.5 pt-0.5 text-[11px] font-medium text-muted-foreground">
          Visible fields
        </div>
        {isGrouped ? (
          <>
            <FieldGroupSection title="Standard fields" fields={standardFields} selectedIds={selectedIds} onToggle={onToggle} disabledReasons={disabledReasons} />
            <FieldGroupSection title="Custom fields" fields={customFields} selectedIds={selectedIds} onToggle={onToggle} disabledReasons={disabledReasons} />
          </>
        ) : (
          fields.map((f) => (
            <FieldCheckboxItem key={f.field} field={f} selectedIds={selectedIds} onToggle={onToggle} disabledReasons={disabledReasons} />
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
