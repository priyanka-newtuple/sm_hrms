import { useEffect, useMemo, useState } from 'react';
import { Filter, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useAuth } from '../../../../core/auth';
import { organizations } from '../../../../core/services/api';
import { useEntityTypes } from '../../../../core/hooks/useEntityTypes';
import {
  globalEntityFilterSettingsFromOrg,
  type GlobalEntityFilterSettings,
} from '../../../../core/contexts/GlobalEntityFilterContext';

function settingsEqual(a: GlobalEntityFilterSettings, b: GlobalEntityFilterSettings): boolean {
  return (
    a.enabled === b.enabled &&
    a.anchorEntityType === b.anchorEntityType &&
    a.placement === b.placement
  );
}

/**
 * Settings tab for configuring the org-level global entity filter.
 * Controls enablement, anchor entity type, and top-bar placement.
 */
export default function GlobalFilterTab() {
  const { organization, refreshOrganization } = useAuth();
  const { summaries, loading: entityTypesLoading } = useEntityTypes();
  const saved = useMemo(
    () => globalEntityFilterSettingsFromOrg(organization?.settings),
    [organization?.settings],
  );
  const [draft, setDraft] = useState<GlobalEntityFilterSettings>(saved);
  const [saving, setSaving] = useState(false);

  useEffect(() => setDraft(saved), [saved]);

  const activeEntityTypes = summaries.filter((type) => {
    if (!type.features) return true;
    return type.features.has_form || type.features.has_lifecycle;
  });
  const isDirty = !settingsEqual(draft, saved);

  const handleSave = async () => {
    setSaving(true);
    try {
      await organizations.updateBranding({
        settings: {
          globalEntityFilter: {
            enabled: draft.enabled,
            anchorEntityType: draft.enabled ? draft.anchorEntityType : null,
            placement: draft.placement,
          },
        },
      });
      await refreshOrganization();
      toast.success('Global filter settings saved');
    } catch (error) {
      toast.error('Could not save global filter settings', {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <div className="mb-1 flex items-center gap-2">
        <Filter className="h-5 w-5 text-cobalt" />
        <h2 className="text-lg font-medium text-foreground">Global entity filter</h2>
      </div>
      <p className="mb-6 text-sm text-muted-foreground">
        Show a top-bar record filter for client-facing workflow pages. The selected
        record filters workflows to that record and directly related records.
      </p>

      <div className="divide-y divide-border rounded-2xl border border-border bg-card">
        <div className="flex items-center justify-between gap-4 p-4">
          <div>
            <div className="text-sm font-medium text-foreground">Enable global filter</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              When enabled, users can pick one record of the configured type from the top bar.
            </p>
          </div>
          <Switch
            checked={draft.enabled}
            onCheckedChange={(enabled: boolean) =>
              setDraft((prev) => ({ ...prev, enabled }))
            }
            disabled={saving}
            aria-label="Enable global entity filter"
          />
        </div>

        <div className="p-4">
          <label className="mb-2 block text-sm font-medium text-foreground">
            Filter entity type
          </label>
          <Select
            value={draft.anchorEntityType ?? ''}
            onValueChange={(anchorEntityType) =>
              setDraft((prev) => ({ ...prev, anchorEntityType: anchorEntityType || null }))
            }
          >
            <SelectTrigger disabled={!draft.enabled || saving || entityTypesLoading}>
              <SelectValue
                placeholder={entityTypesLoading ? 'Loading entity types…' : 'Select entity type'}
              />
            </SelectTrigger>
            <SelectContent>
              {activeEntityTypes.map((type) => (
                <SelectItem key={type.id} value={type.name}>
                  {type.display_name || type.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="mt-2 text-xs text-muted-foreground">
            Users will search records from this entity type only. They cannot change the type.
          </p>
        </div>

        <div className="p-4">
          <label className="mb-2 block text-sm font-medium text-foreground">
            Filter position
          </label>
          <Select
            value={draft.placement}
            onValueChange={(placement) =>
              setDraft((prev) => ({
                ...prev,
                placement: placement === 'left' ? 'left' : 'right',
              }))
            }
          >
            <SelectTrigger disabled={!draft.enabled || saving}>
              <SelectValue placeholder="Select position" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="left">Top left</SelectItem>
              <SelectItem value="right">Top right</SelectItem>
            </SelectContent>
          </Select>
          <p className="mt-2 text-xs text-muted-foreground">
            Choose whether the selector appears near the start of the top bar or with the
            top-bar actions.
          </p>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={!isDirty || saving || (draft.enabled && !draft.anchorEntityType)}
        >
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Save
        </Button>
        <Button
          variant="ghost"
          onClick={() => setDraft(saved)}
          disabled={!isDirty || saving}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
