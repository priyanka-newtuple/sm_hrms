/**
 * The "Read only" switch, shared by the two field editors (Settings -> Fields
 * and the Forms tab's field row) so the copy and behaviour cannot drift.
 *
 * Deliberately not `editable`: that one is engine-computed and forced false
 * for inherited and calculated fields. This is the administrator's own
 * value-level lock.
 */

import { Switch } from '@/components/ui/switch';

interface ReadOnlyToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  /** Keeps the switch id unique when several editors are on one page. */
  id?: string;
}

export default function ReadOnlyToggle({
  checked,
  onCheckedChange,
  disabled = false,
  id,
}: ReadOnlyToggleProps) {
  return (
    <div className="flex items-center justify-between py-1">
      <div>
        <span className="text-sm font-medium text-foreground">Read only</span>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Its value can&apos;t be edited, regardless of who&apos;s viewing.
        </p>
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  );
}
