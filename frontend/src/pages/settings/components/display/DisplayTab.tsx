/**
 * DisplayTab
 *
 * Lets an organization admin toggle which parts of the app are visible for
 * their organization — the Kanban board, Dashboard, Agent Mode, and Records.
 * Saved under `settings.featureFlags` on the organization (shallow-merged
 * server-side, so branding theme settings are unaffected).
 */

import { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Loader2, MonitorCog } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { useAuth } from '../../../../core/auth';
import { organizations } from '../../../../core/services/api';
import {
  FEATURE_FLAG_DEFAULTS,
  featureFlagsFromSettings,
  type FeatureFlags,
} from '../../../../core/hooks/useFeatureFlags';

/**
 * Toggle rows. Copy is phrased positively ("Show …") by default, so the switch
 * being ON means visible and the stored `hide*` value is the inverse — except
 * rows marked `direct: true`, where the switch maps straight to the stored
 * value with no inversion (used when the row's own label is already the
 * "hide" action, e.g. "Hide Entities").
 */
const FLAG_ROWS: Array<{
  key: keyof FeatureFlags;
  label: string;
  description: string;
  direct?: boolean;
}> = [
    {
      key: 'hideKanban',
      label: 'Kanban board',
      description: 'Show the Kanban view on pipeline pages. When off, only the List view is available.',
    },
    {
      key: 'hideCalendar',
      label: 'Calendar view',
      description: 'Show the Calendar view on pipeline pages. Requires the Due date feature.',
    },
    {
      key: 'hideDueDate',
      label: 'Due date',
      description: 'Show Due date when creating, viewing, and listing entities. Turning this off also hides Calendar.',
    },
    {
      key: 'hideDashboard',
      label: 'Dashboard',
      description: 'Show the Dashboard item in the navigation sidebar.',
    },
    {
      key: 'hideAgent',
      label: 'Agent Mode',
      description: 'Show the Agent toggle in the top bar and the agent sidebar.',
    },
    {
      key: 'hideRecords',
      label: 'Records',
      description: 'Show the Records item in the navigation sidebar.',
    },
    {
      key: 'hideWhatsNew',
      label: "What's New",
      description: "Show the What's New changelog item in the navigation sidebar. Off by default.",
    },
    {
      key: 'hideExport',
      label: 'Export',
      description: 'Show the Export button on pipeline pages.',
    },
    {
      key: 'hideRerunAction',
      label: 'Re-run action',
      description: 'Show the Re-run action control on the entity detail view.',
    },
    {
      key: 'bulkImportEnabled',
      label: 'Bulk import',
      description:
        'Allow authorized users to upload mixed documents, review AI-proposed entities, and create them in bulk.',
      direct: true,
    },
    {
      key: 'cardFieldsEnabled',
      label: 'Card fields',
      description:
        'Let workflow admins pick up to 3 extra entity fields to show on Kanban cards. Off by default.',
      direct: true,
    },
    {
      key: 'hideAssigneeFilter',
      label: 'Assignee filter',
      description:
        'Show the assignee avatar filter on Board, Table, and Calendar. Off by default.',
    },
    {
      key: 'hideTerminalByDefault',
      label: 'Hide Terminal Entities',
      description:
        'Hide entities in a terminal state (e.g. Rejected, Withdrawn) on every pipeline board. Same setting as the Show/Hide control on the board toolbar - changing it here or there changes it everywhere.',
      direct: true,
    },
    {
      key: 'sendAssignmentEmails',
      label: 'Assignment emails',
      description: 'Email the new assignee when an entity is assigned to them. Off by default.',
      direct: true,
    },
    {
      key: 'sendCommentEmails',
      label: 'Comment emails',
      description: 'Email the mentioned user and the entity\'s assignee when a comment is made. Off by default.',
      direct: true,
    },
    {
      key: 'sendReplyEmails',
      label: 'Reply emails',
      description: 'Email a top-level comment\'s author when someone replies to it. Off by default.',
      direct: true,
    },
    {
      key: 'sendLikeEmails',
      label: 'Like emails',
      description: 'Email a comment\'s author when someone likes it. Off by default — likes are high-frequency and low-signal.',
      direct: true,
    },
    {
      key: 'darkModeEnabled',
      label: 'Dark mode',
      description:
        'Let everyone in your organization choose Light, Dark, or System from their account menu. Off by default; when off the app stays light for all members.',
      direct: true,
    },
  ];

function flagsEqual(a: FeatureFlags, b: FeatureFlags): boolean {
  return (
    a.hideKanban === b.hideKanban &&
    a.hideCalendar === b.hideCalendar &&
    a.hideDueDate === b.hideDueDate &&
    a.hideDashboard === b.hideDashboard &&
    a.hideAgent === b.hideAgent &&
    a.hideRecords === b.hideRecords &&
    a.hideWhatsNew === b.hideWhatsNew &&
    a.hideExport === b.hideExport &&
    a.hideRerunAction === b.hideRerunAction &&
    a.bulkImportEnabled === b.bulkImportEnabled &&
    a.cardFieldsEnabled === b.cardFieldsEnabled &&
    a.hideAssigneeFilter === b.hideAssigneeFilter &&
    a.entityDetailFullPage === b.entityDetailFullPage &&
    a.hideTerminalByDefault === b.hideTerminalByDefault &&
    a.sendAssignmentEmails === b.sendAssignmentEmails &&
    a.sendCommentEmails === b.sendCommentEmails &&
    a.sendReplyEmails === b.sendReplyEmails &&
    a.sendLikeEmails === b.sendLikeEmails &&
    a.darkModeEnabled === b.darkModeEnabled
  );
}

/** Mini skeleton of a pipeline board with the detail sheet over its right edge. */
function SheetPreview() {
  return (
    <div className="relative h-24 w-full overflow-hidden rounded-lg border border-border bg-muted">
      <div className="absolute inset-0 p-2">
        <div className="mb-1.5 h-1.5 w-10 rounded-full bg-accent" />
        <div className="flex gap-1.5">
          <div className="h-14 w-1/4 rounded bg-accent" />
          <div className="h-14 w-1/4 rounded bg-accent" />
          <div className="h-14 w-1/4 rounded bg-accent" />
        </div>
      </div>
      <div className="absolute inset-y-0 right-0 w-2/5 rounded-l-lg border-l border-cobalt/30 bg-card p-2 shadow-sm">
        <div className="mb-1.5 h-1.5 w-8 rounded-full bg-cobalt/60" />
        <div className="mb-1 h-1 w-full rounded-full bg-accent" />
        <div className="mb-1 h-1 w-3/4 rounded-full bg-accent" />
        <div className="h-1 w-1/2 rounded-full bg-accent" />
      </div>
    </div>
  );
}

/** Mini skeleton of the full-page detail view under the top nav bar. */
function FullPagePreview() {
  return (
    <div className="h-24 w-full overflow-hidden rounded-lg border border-border bg-muted">
      <div className="flex h-4 items-center gap-1 border-b border-border bg-card px-2">
        <div className="h-1 w-6 rounded-full bg-cobalt/60" />
        <div className="h-1 w-4 rounded-full bg-accent" />
      </div>
      <div className="p-2">
        <div className="mb-1.5 h-1.5 w-12 rounded-full bg-cobalt/60" />
        <div className="mb-1 h-1 w-full rounded-full bg-accent" />
        <div className="mb-1 h-1 w-5/6 rounded-full bg-accent" />
        <div className="h-8 w-full rounded border border-border bg-card" />
      </div>
    </div>
  );
}

type ViewModeCardProps = {
  label: string;
  description: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
  preview: React.ReactNode;
};

function ViewModeCard({ label, description, selected, disabled, onSelect, preview }: ViewModeCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      aria-pressed={selected}
      className={[
        'rounded-2xl border bg-card p-3 text-left transition-colors disabled:opacity-60',
        selected ? 'border-cobalt ring-1 ring-cobalt' : 'border-border hover:border-border',
      ].join(' ')}
    >
      {preview}
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-foreground">{label}</div>
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        </div>
        {selected ? (
          <CheckCircle2 className="h-5 w-5 shrink-0 text-cobalt" />
        ) : (
          <Circle className="h-5 w-5 shrink-0 text-muted-foreground/60" />
        )}
      </div>
    </button>
  );
}

export default function DisplayTab() {
  const { organization, refreshOrganization } = useAuth();
  const saved = featureFlagsFromSettings(organization?.settings);

  const [draft, setDraft] = useState<FeatureFlags>(saved);
  const [saving, setSaving] = useState(false);

  // Re-seed the draft when the active organization (or its settings) changes.
  useEffect(() => {
    setDraft(featureFlagsFromSettings(organization?.settings));
  }, [organization?.settings]);

  const isDirty = !flagsEqual(draft, saved);

  const setFlag = (key: keyof FeatureFlags, visible: boolean) =>
    setDraft((prev) => ({
      ...prev,
      [key]: !visible,
      ...(key === 'hideDueDate' && !visible ? { hideCalendar: true } : {}),
    }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await organizations.updateBranding({ settings: { featureFlags: draft } });
      await refreshOrganization();
      toast.success('Display settings saved');
    } catch (e) {
      toast.error('Could not save display settings', {
        description: e instanceof Error ? e.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-2 mb-1">
        <MonitorCog className="w-5 h-5 text-cobalt" />
        <h2 className="text-lg font-medium text-foreground">Display</h2>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Choose which parts of the app are visible for everyone in your organization.
      </p>

      <div className="divide-y divide-border rounded-2xl border border-border bg-card">
        {FLAG_ROWS.map(({ key, label, description, direct }) => (
          <div key={key} className="flex items-center justify-between gap-4 p-4">
            <div>
              <div className="text-sm font-medium text-foreground">{label}</div>
              <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
            </div>
            <Switch
              checked={
                direct
                  ? draft[key]
                  : !draft[key] && !(key === 'hideCalendar' && draft.hideDueDate)
              }
              onCheckedChange={(checked: boolean) =>
                direct
                  ? setDraft((prev) => ({ ...prev, [key]: checked }))
                  : setFlag(key, checked)
              }
              disabled={saving || (key === 'hideCalendar' && draft.hideDueDate)}
              aria-label={direct ? label : `Show ${label}`}
            />
          </div>
        ))}
      </div>

      {/* Entity detail view mode — visual picker (positive flag, not an inverted "Show …" row) */}
      <div className="mt-6">
        <div className="text-sm font-medium text-foreground">Entity detail view</div>
        <p className="text-xs text-muted-foreground mt-0.5 mb-3">How entity details open from pipeline boards.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <ViewModeCard
            label="Slide-over sheet"
            description="Opens as a panel over the board."
            selected={!draft.entityDetailFullPage}
            disabled={saving}
            onSelect={() => setDraft((prev) => ({ ...prev, entityDetailFullPage: false }))}
            preview={<SheetPreview />}
          />
          <ViewModeCard
            label="Full page"
            description="Opens as its own page under the nav bar."
            selected={draft.entityDetailFullPage}
            disabled={saving}
            onSelect={() => setDraft((prev) => ({ ...prev, entityDetailFullPage: true }))}
            preview={<FullPagePreview />}
          />
        </div>
      </div>

      <div className="flex items-center gap-3 mt-6">
        <Button variant="primary" onClick={handleSave} disabled={!isDirty || saving}>
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          Save
        </Button>
        <Button
          variant="ghost"
          onClick={() => setDraft(saved)}
          disabled={!isDirty || saving}
        >
          Cancel
        </Button>
        <Button
          variant="ghost-action"
          onClick={() => setDraft(FEATURE_FLAG_DEFAULTS)}
          disabled={saving || flagsEqual(draft, FEATURE_FLAG_DEFAULTS)}
          className="ml-auto"
        >
          Reset to default
        </Button>
      </div>
    </div>
  );
}
