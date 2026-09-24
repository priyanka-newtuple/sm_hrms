/**
 * AppLabelsTab
 *
 * Lets an organization admin rename the main-app section labels (Dashboard,
 * Workflows, Records, Pipeline) for the whole org. Each rename applies to the
 * sidebar nav, breadcrumb, and page heading for that section. Stored in the org
 * settings JSON under `appLabels` and applied live via `useAppLabels`.
 */

import { useEffect, useMemo, useState } from 'react';
import { Loader2, RotateCcw, Type } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useAuth } from '../../../../core/auth';
import { organizations } from '../../../../core/services/api';
import { getCurrentOrganizationId } from '../../../../core/services/api/client';
import {
  APP_LABEL_FIELDS,
  type AppLabels,
} from '@/shared/hooks';

function labelsFromSettings(settings: Record<string, unknown> | undefined): Partial<AppLabels> {
  return (settings?.appLabels as Partial<AppLabels> | undefined) ?? {};
}

export default function AppLabelsTab() {
  const { organization, refreshOrganization } = useAuth();
  const orgId = organization?.id || getCurrentOrganizationId();

  const saved = useMemo(
    () => labelsFromSettings(organization?.settings),
    [organization?.settings],
  );

  const [draft, setDraft] = useState<Partial<AppLabels>>(saved);
  const [saving, setSaving] = useState(false);

  useEffect(() => setDraft(saved), [saved]);

  const isDirty = APP_LABEL_FIELDS.some(
    ({ key }) => (draft[key] ?? '') !== (saved[key] ?? ''),
  );

  const set = (key: keyof AppLabels, value: string) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    if (!orgId) {
      toast.error('No active organization to save to.');
      return;
    }
    setSaving(true);
    try {
      // Only persist non-empty overrides; empty falls back to the default.
      const appLabels: Partial<AppLabels> = {};
      for (const { key } of APP_LABEL_FIELDS) {
        const v = (draft[key] ?? '').trim();
        if (v) appLabels[key] = v;
      }
      await organizations.updateBranding({ settings: { appLabels } });
      await refreshOrganization();
      toast.success('App labels saved');
    } catch (e) {
      toast.error('Could not save app labels', {
        description: e instanceof Error ? e.message : 'Failed to save',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setDraft({});
  };

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
          <Type className="h-5 w-5 text-cobalt" />
          App labels
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Rename the main navigation sections for your organization. Each name is
          used in the sidebar, breadcrumbs, and page title. Leave blank to use the
          default.
        </p>
      </div>

      <div className="space-y-4">
        {APP_LABEL_FIELDS.map(({ key, defaultLabel }) => (
          <div key={key} className="space-y-1.5">
            <label className="block text-sm font-medium text-foreground">
              {defaultLabel} section
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
        Defaults: {APP_LABEL_FIELDS.map((f) => `${f.defaultLabel}`).join(', ')}.
      </p>
    </div>
  );
}
