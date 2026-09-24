// This is a widget registry: it deliberately co-exports the registry data
// (EMBEDDED_WIDGETS, getEmbeddedWidget) alongside its render/config components,
// so Fast Refresh's "only export components" rule doesn't apply here.
/* eslint-disable react-refresh/only-export-components */
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Input, Select } from '../../../core/components';
import { Checkbox } from '@/components/ui/checkbox';
import { useWorkflows } from '@/shared/hooks';
import WorkflowsListWidget from '../../Workflows/WorkflowsListWidget';
import PipelineBoardWidget from '../../Pipeline/PipelineBoardWidget';

/** Per-widget config blob stored in the dashboard JSON (`componentConfig`). */
export type EmbeddedWidgetConfig = Record<string, unknown>;

export interface EmbeddedConfigFormProps {
  value: EmbeddedWidgetConfig;
  onChange: (next: EmbeddedWidgetConfig) => void;
}

/** A curated embedded widget: a reusable feature component the dashboard may
 *  host. Embedded widgets fetch through their own domain hooks/APIs — they are
 *  never routed through POST /dashboards/data. */
export interface EmbeddedWidgetEntry {
  componentKey: string;
  label: string;
  description: string;
  defaultLayout: { w: number; h: number };
  /** Seeded into `componentConfig` when the widget is first picked in the builder. */
  defaultConfig: EmbeddedWidgetConfig;
  supportsAutoHeight?: (config: EmbeddedWidgetConfig) => boolean;
  render: (config: EmbeddedWidgetConfig, options?: { autoHeight?: boolean }) => ReactNode;
  ConfigForm: (props: EmbeddedConfigFormProps) => ReactNode;
}

function asBool(v: unknown, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function CheckboxField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-foreground">
      <Checkbox checked={checked} onCheckedChange={(next) => onChange(next === true)} />
      {label}
    </label>
  );
}

function WorkflowsListConfigForm({ value, onChange }: EmbeddedConfigFormProps) {
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const fields = Array.isArray(value.defaultVisibleFields)
    ? (value.defaultVisibleFields as string[])
    : [];
  return (
    <>
      <Input
        label="Entity type filter (optional)"
        placeholder="e.g. candidate"
        value={typeof value.entityTypeFilter === 'string' ? value.entityTypeFilter : ''}
        onChange={(e) => set('entityTypeFilter', e.target.value)}
      />
      <Input
        label="Default visible fields (optional, comma-separated)"
        placeholder="workflow, owner"
        value={fields.join(', ')}
        onChange={(e) =>
          set(
            'defaultVisibleFields',
            e.target.value
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean),
          )
        }
      />
      <div className="space-y-2">
        <CheckboxField
          label="Show row transitions"
          checked={asBool(value.showTransitions, true)}
          onChange={(v) => set('showTransitions', v)}
        />
        <CheckboxField
          label="Show header inside widget"
          checked={asBool(value.showHeader, false)}
          onChange={(v) => set('showHeader', v)}
        />
        <CheckboxField
          label="Compact"
          checked={asBool(value.compact, true)}
          onChange={(v) => set('compact', v)}
        />
      </div>
    </>
  );
}

const workflowsList: EmbeddedWidgetEntry = {
  componentKey: 'workflows.list',
  label: 'Workflows List',
  description: 'The interactive workflows list with row transitions and entity details.',
  defaultLayout: { w: 30, h: 6 },
  defaultConfig: { showTransitions: true, showHeader: false, compact: true },
  supportsAutoHeight: () => true,
  render: (config, options) => (
    <WorkflowsListWidget
      compact={asBool(config.compact, true)}
      autoHeight={options?.autoHeight}
      showHeader={asBool(config.showHeader, false)}
      showTransitions={asBool(config.showTransitions, true)}
      entityTypeFilter={
        typeof config.entityTypeFilter === 'string' && config.entityTypeFilter
          ? config.entityTypeFilter
          : undefined
      }
      defaultVisibleFields={
        Array.isArray(config.defaultVisibleFields)
          ? (config.defaultVisibleFields as string[])
          : undefined
      }
    />
  ),
  ConfigForm: WorkflowsListConfigForm,
};

function PipelineBoardConfigForm({ value, onChange }: EmbeddedConfigFormProps) {
  const { workflows, loading } = useWorkflows();
  const set = (key: string, v: unknown) => onChange({ ...value, [key]: v });
  const view = value.view === 'kanban' ? 'kanban' : 'list';
  return (
    <>
      <Select
        label="Pipeline"
        placeholder={loading ? 'Loading pipelines…' : 'Choose a pipeline'}
        value={typeof value.workflowId === 'string' ? value.workflowId : ''}
        options={workflows.map((w) => ({ value: w.id, label: w.label }))}
        onChange={(e) => set('workflowId', e.target.value)}
      />
      <Select
        label="View"
        value={view}
        options={[
          { value: 'list', label: 'List' },
          { value: 'kanban', label: 'Kanban' },
        ]}
        onChange={(e) => set('view', e.target.value)}
      />
      {view === 'list' && (
        <CheckboxField
          label="Show row transitions"
          checked={asBool(value.showTransitions, true)}
          onChange={(v) => set('showTransitions', v)}
        />
      )}
    </>
  );
}

const pipelineBoard: EmbeddedWidgetEntry = {
  componentKey: 'pipeline.board',
  label: 'Pipeline Board',
  description: 'One pipeline as an interactive list or kanban, with entity details.',
  defaultLayout: { w: 30, h: 6 },
  defaultConfig: { view: 'list', showTransitions: true },
  supportsAutoHeight: (config) => config.view !== 'kanban',
  render: (config, options) =>
    typeof config.workflowId === 'string' && config.workflowId ? (
      <PipelineBoardWidget
        workflowId={config.workflowId}
        view={config.view === 'kanban' ? 'kanban' : 'list'}
        autoHeight={options?.autoHeight}
        showTransitions={asBool(config.showTransitions, true)}
      />
    ) : (
      <div className="text-sm text-muted-foreground">
        No pipeline selected. Edit the widget and choose one.
      </div>
    ),
  ConfigForm: PipelineBoardConfigForm,
};

/** Validates a user-supplied embed URL. Returns the normalized href or undefined.
 *  Security:
 *   - http(s) only — blocks javascript:/data:/blob: src injection.
 *   - Rejects same-origin URLs. With sandbox="allow-scripts allow-same-origin",
 *     a same-origin frame can strip its own sandbox and run our app's JS with the
 *     viewer's session; external origins stay contained by the sandbox. */
function safeEmbedUrl(v: unknown): string | undefined {
  if (typeof v !== 'string' || !v.trim()) return undefined;
  try {
    const u = new URL(v.trim(), window.location.origin);
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return undefined;
    // An http iframe is active mixed content — browsers block it on an https
    // page, so reject it here rather than saving a silently-broken widget.
    if (u.protocol === 'http:' && window.location.protocol === 'https:') return undefined;
    if (u.origin === window.location.origin) return undefined;
    return u.href;
  } catch {
    return undefined;
  }
}

function EmbedLinkConfigForm({ value, onChange }: EmbeddedConfigFormProps) {
  const url = typeof value.url === 'string' ? value.url : '';
  const invalid = url.trim() !== '' && !safeEmbedUrl(url);
  return (
    <>
      <Input
        label="Embed URL (https://…)"
        placeholder="https://example.com/embed/abc"
        value={url}
        onChange={(e) => onChange({ ...value, url: e.target.value })}
      />
      {invalid && (
        <p className="text-xs text-destructive">
          Enter a valid external http(s) URL (this app&apos;s own pages can&apos;t be embedded).
        </p>
      )}
      <CheckboxField
        label="Allow fullscreen"
        checked={asBool(value.allowFullscreen, true)}
        onChange={(v) => onChange({ ...value, allowFullscreen: v })}
      />
    </>
  );
}

const embedLink: EmbeddedWidgetEntry = {
  componentKey: 'embed.link',
  label: 'Embed Link',
  description: 'Embed any external page or widget via its URL (rendered in a sandboxed iframe).',
  defaultLayout: { w: 30, h: 6 },
  defaultConfig: { url: '', allowFullscreen: true },
  render: (config) => {
    const url = safeEmbedUrl(config.url);
    if (!url) {
      return (
        <div className="text-sm text-muted-foreground">
          No URL set. Edit the widget and paste an http(s) link.
        </div>
      );
    }
    return (
      <iframe
        src={url}
        title="Embedded content"
        className="h-full w-full rounded-lg border border-border"
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        referrerPolicy="no-referrer"
        allow={asBool(config.allowFullscreen, true) ? 'fullscreen' : undefined}
      />
    );
  },
  ConfigForm: EmbedLinkConfigForm,
};

export const EMBEDDED_WIDGETS: EmbeddedWidgetEntry[] = [workflowsList, pipelineBoard, embedLink];

export function getEmbeddedWidget(key?: string): EmbeddedWidgetEntry | undefined {
  return EMBEDDED_WIDGETS.find((e) => e.componentKey === key);
}

/** A failing embedded widget must not take down the rest of the dashboard. */
export class EmbeddedWidgetBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Embedded widget crashed:', error, info);
  }
  render() {
    if (this.state.failed) {
      return <div className="text-sm text-destructive">This widget failed to render.</div>;
    }
    return this.props.children;
  }
}
