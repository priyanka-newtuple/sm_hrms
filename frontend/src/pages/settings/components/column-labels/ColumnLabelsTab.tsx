/**
 * ColumnLabelsTab
 *
 * Lets an organization admin rename the list-view column headers (Name,
 * Workflow, Owner, Status, Created) for the whole org. Stored in the org
 * settings JSON under `columnLabels` and applied live via `useColumnLabels`.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2, RotateCcw, Columns3 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '../../../../core/auth';
import { organizations } from '../../../../core/services/api';
import { getCurrentOrganizationId } from '../../../../core/services/api/client';
import {
  COLUMN_LABEL_FIELDS,
  COLUMN_LABEL_DEFAULTS,
  type ColumnLabels,
} from '@/shared/hooks';

function labelsFromSettings(settings: Record<string, unknown> | undefined): Partial<ColumnLabels> {
  return (settings?.columnLabels as Partial<ColumnLabels> | undefined) ?? {};
}

export default function ColumnLabelsTab() {
  const { organization, refreshOrganization } = useAuth();
  const orgId = organization?.id || getCurrentOrganizationId();

  const saved = useMemo(
    () => labelsFromSettings(organization?.settings),
    [organization?.settings],
  );

  const [draft, setDraft] = useState<Partial<ColumnLabels>>(saved);
  const [saving, setSaving] = useState(false);

  useEffect(() => setDraft(saved), [saved]);

  const isDirty = COLUMN_LABEL_FIELDS.some(
    ({ key }) => (draft[key] ?? '') !== (saved[key] ?? ''),
  );

  const set = (key: keyof ColumnLabels, value: string) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    if (!orgId) {
      toast.error('No active organization to save to.');
      return;
    }
    setSaving(true);
    try {
      // Only persist non-empty overrides; empty falls back to the default.
      const columnLabels: Partial<ColumnLabels> = {};
      for (const { key } of COLUMN_LABEL_FIELDS) {
        const v = (draft[key] ?? '').trim();
        if (v) columnLabels[key] = v;
      }
      await organizations.updateBranding({ settings: { columnLabels } });
      await refreshOrganization();
      toast.success('Column labels saved');
    } catch (e) {
      toast.error('Could not save column labels', {
        description: e instanceof Error ? e.message : 'Failed to save',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    const cleared: Partial<ColumnLabels> = {};
    setDraft(cleared);
  };

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
          <Columns3 className="h-5 w-5 text-cobalt" />
          Column labels
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Rename the list-view column headers for your organization. Leave blank
          to use the default.
        </p>
      </div>

      <div className="space-y-4">
        {COLUMN_LABEL_FIELDS.map(({ key, defaultLabel }) => (
          <div key={key} className="space-y-1.5">
            <label className="block text-sm font-medium text-foreground capitalize">
              {key} column
            </label>
            <input
              type="text"
              value={draft[key] ?? ''}
              onChange={(e) => set(key, e.target.value)}
              placeholder={`${defaultLabel} (default)`}
              className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground/70 focus:border-cobalt/40 focus:outline-none focus:ring-2 focus:ring-cobalt/10"
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={!isDirty || saving} variant="primary">
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save
        </Button>
        <Button onClick={handleReset} variant="ghost" disabled={saving}>
          <RotateCcw className="mr-2 h-4 w-4" />
          Reset to defaults
        </Button>
      </div>

      <p className="text-xs text-muted-foreground/80">
        Defaults: {COLUMN_LABEL_FIELDS.map((f) => `${f.key} → ${COLUMN_LABEL_DEFAULTS[f.key]}`).join(', ')}.
      </p>
    </div>
  );
}
