import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react';
import {
  AlertBanner,
  Button,
  ColumnOrderPicker,
  IconPicker,
  Input,
  Modal,
  Select,
} from '../../../core/components';
import { QueryBuilderForm } from './QueryBuilderForm';
import type {
  DashboardContentElement,
  DashboardFilterOption,
  DashboardFilterOptionsResponse,
  DashboardMetricRead,
  DashboardViz,
} from '../../../core/types';
import {
  ALIGN_OPTIONS,
  CARTESIAN_VIZ,
  type BuilderState,
  CONTENT_ELEMENT_KINDS,
  METADATA_TYPE_OPTIONS,
  NUMBER_PRESETS,
  VERTICAL_ALIGN_OPTIONS,
  WIDGET_KINDS,
  type WidgetKind,
} from '../lib/constants';
import { EMBEDDED_WIDGETS, getEmbeddedWidget } from '../lib/embeddedWidgets';
import { vizOptionsFor } from '../lib/utils';

export interface WidgetBuilderModalProps {
  open: boolean;
  editingId: string | null;
  builder: BuilderState;
  setBuilder: React.Dispatch<React.SetStateAction<BuilderState>>;
  onClose: () => void;
  onPickKind: (kind: WidgetKind) => void;
  onPickMetric: (key: string) => void;
  onSubmit: () => void;
  kindMetrics: DashboardMetricRead[];
  selectedMetric: DashboardMetricRead | undefined;
  filterOptions: DashboardFilterOptionsResponse;
  /** True when the server couldn't resolve custom fields for the workflow and
   *  the picker has been restricted to built-in workflow columns. */
  fieldsScopeWarning: boolean;
  scopedOptionsLoading: boolean;
  scopedOptionsError: string | null;
  onRetryScopedOptions: () => void;
}

export function WidgetBuilderModal({
  open,
  editingId,
  builder,
  setBuilder,
  onClose,
  onPickKind,
  onPickMetric,
  onSubmit,
  kindMetrics,
  selectedMetric,
  filterOptions,
  fieldsScopeWarning,
  scopedOptionsLoading,
  scopedOptionsError,
  onRetryScopedOptions,
}: WidgetBuilderModalProps) {
  const addElement = () => {
    const el: DashboardContentElement = {
      id: `el-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      kind: 'text',
      text: '',
      align: 'left',
    };
    setBuilder((prev) => ({ ...prev, elements: [...prev.elements, el] }));
  };
  const updateElement = (idx: number, patch: Partial<DashboardContentElement>) => {
    setBuilder((prev) => ({
      ...prev,
      elements: prev.elements.map((el, i) => (i === idx ? { ...el, ...patch } : el)),
    }));
  };
  const moveElement = (idx: number, dir: -1 | 1) => {
    setBuilder((prev) => {
      const next = [...prev.elements];
      const target = idx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return { ...prev, elements: next };
    });
  };
  const removeElement = (idx: number) => {
    setBuilder((prev) => ({ ...prev, elements: prev.elements.filter((_, i) => i !== idx) }));
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editingId ? 'Edit widget' : 'Add widget'}
      size="md"
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <span className="text-sm font-medium text-foreground">Widget kind</span>
          <div className="grid grid-cols-2 gap-2">
            {WIDGET_KINDS.map((opt) => {
              const Icon = opt.icon;
              const active = builder.kind === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => onPickKind(opt.value)}
                  className={
                    active
                      ? 'flex items-start gap-3 rounded-xl border border-cobalt bg-cobalt/5 p-3 text-left ring-1 ring-cobalt'
                      : 'flex items-start gap-3 rounded-xl border border-border p-3 text-left hover:bg-muted'
                  }
                >
                  <Icon
                    className={active ? 'h-5 w-5 text-cobalt' : 'h-5 w-5 text-muted-foreground'}
                    strokeWidth={1.5}
                  />
                  <span className="space-y-0.5">
                    <span className="block text-sm font-medium text-foreground">{opt.label}</span>
                    <span className="block text-xs text-muted-foreground">{opt.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {builder.kind === 'query' ? (
          <>
            <Input
              label="Title"
              value={builder.title}
              onChange={(e) => setBuilder((prev) => ({ ...prev, title: e.target.value }))}
            />
            <QueryBuilderForm
              value={builder.query}
              onChange={(query) => setBuilder((prev) => ({ ...prev, query }))}
              viz={builder.viz}
              onVizChange={(viz) => setBuilder((prev) => ({ ...prev, viz }))}
            />
          </>
        ) : builder.kind === 'embedded' ? (
          <>
            <Select
              label="Widget"
              placeholder="Choose a widget"
              value={builder.componentKey}
              options={EMBEDDED_WIDGETS.map((e) => ({ value: e.componentKey, label: e.label }))}
              onChange={(e) => {
                const entry = getEmbeddedWidget(e.target.value);
                setBuilder((prev) => ({
                  ...prev,
                  componentKey: e.target.value,
                  title: prev.title || entry?.label || '',
                  componentConfig: entry ? { ...entry.defaultConfig } : {},
                }));
              }}
            />
            {(() => {
              const entry = getEmbeddedWidget(builder.componentKey);
              if (!entry) return null;
              return (
                <>
                  <p className="text-xs text-muted-foreground">{entry.description}</p>
                  <Input
                    label="Title"
                    value={builder.title}
                    onChange={(e) => setBuilder((prev) => ({ ...prev, title: e.target.value }))}
                  />
                  <entry.ConfigForm
                    value={builder.componentConfig}
                    onChange={(next) => setBuilder((prev) => ({ ...prev, componentConfig: next }))}
                  />
                </>
              );
            })()}
          </>
        ) : builder.kind === 'content' ? (
          <>
            <div className="space-y-1.5">
              <span className="text-sm font-medium text-foreground">Vertical align</span>
              <div className="flex gap-2">
                {VERTICAL_ALIGN_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setBuilder((prev) => ({ ...prev, verticalAlign: opt.value }))}
                    className={
                      builder.verticalAlign === opt.value
                        ? 'rounded-full border border-cobalt bg-cobalt/10 px-3 py-1 text-sm font-medium text-cobalt'
                        : 'rounded-full border border-border px-3 py-1 text-sm text-muted-foreground hover:bg-muted'
                    }
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-3">
              {builder.elements.map((el, idx) => (
                <div key={el.id} className="space-y-2 rounded-xl border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <Select
                      value={el.kind}
                      options={CONTENT_ELEMENT_KINDS}
                      onChange={(e) =>
                        updateElement(idx, { kind: e.target.value as DashboardContentElement['kind'] })
                      }
                    />
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={idx === 0}
                        onClick={() => moveElement(idx, -1)}
                        className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                        aria-label="Move element up"
                      >
                        <ChevronUp className="h-4 w-4" strokeWidth={1.5} />
                      </button>
                      <button
                        type="button"
                        disabled={idx === builder.elements.length - 1}
                        onClick={() => moveElement(idx, 1)}
                        className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                        aria-label="Move element down"
                      >
                        <ChevronDown className="h-4 w-4" strokeWidth={1.5} />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeElement(idx)}
                        className="text-muted-foreground hover:text-destructive"
                        aria-label="Remove element"
                      >
                        <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                      </button>
                    </div>
                  </div>
                  <Input
                    label="Text"
                    value={el.text}
                    onChange={(e) => updateElement(idx, { text: e.target.value })}
                  />
                  {el.kind === 'button' && (
                    <Input
                      label="Navigate to (route)"
                      placeholder="/jobs"
                      value={el.href ?? ''}
                      onChange={(e) => updateElement(idx, { href: e.target.value })}
                    />
                  )}
                  <div className="space-y-1.5">
                    <span className="text-sm font-medium text-foreground">Align</span>
                    <div className="flex gap-2">
                      {ALIGN_OPTIONS.map((opt) => (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => updateElement(idx, { align: opt.value })}
                          className={
                            (el.align ?? 'left') === opt.value
                              ? 'rounded-full border border-cobalt bg-cobalt/10 px-3 py-1 text-sm font-medium text-cobalt'
                              : 'rounded-full border border-border px-3 py-1 text-sm text-muted-foreground hover:bg-muted'
                          }
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Button variant="secondary" size="sm" onClick={addElement}>
              <Plus className="h-4 w-4" strokeWidth={1.5} />
              Add element
            </Button>
          </>
        ) : builder.kind !== 'button' ? (
          <>
            <Select
              label="Metric"
              placeholder={kindMetrics.length ? 'Choose a metric' : 'No metrics available'}
              value={builder.metric}
              options={kindMetrics.map((m) => ({ value: m.key, label: m.label }))}
              onChange={(e) => onPickMetric(e.target.value)}
            />
            {selectedMetric && (
              <p className="text-xs text-muted-foreground">{selectedMetric.description}</p>
            )}
            <Input
              label="Title"
              value={builder.title}
              onChange={(e) => setBuilder((prev) => ({ ...prev, title: e.target.value }))}
            />
            <Input
              label="Subtext (optional)"
              placeholder="Supporting line under the title"
              value={builder.description}
              onChange={(e) => setBuilder((prev) => ({ ...prev, description: e.target.value }))}
            />
            <Input
              label="Title link (optional)"
              placeholder="/jobs"
              value={builder.href}
              onChange={(e) => setBuilder((prev) => ({ ...prev, href: e.target.value }))}
            />
            {builder.kind === 'stat' && selectedMetric && (
              <IconPicker
                label="Icon (optional)"
                value={builder.icon}
                onChange={(next) => setBuilder((prev) => ({ ...prev, icon: next }))}
              />
            )}
            {builder.kind === 'stat' && selectedMetric && (
              <Input
                label="Subtitle (optional)"
                placeholder="{value} units across selected range"
                value={builder.subtitle}
                onChange={(e) => setBuilder((prev) => ({ ...prev, subtitle: e.target.value }))}
              />
            )}
            {selectedMetric?.output === 'series' && (
              <div className="space-y-1.5">
                <span className="text-sm font-medium text-foreground">Visualization</span>
                <div className="flex flex-wrap gap-2">
                  {vizOptionsFor().map((opt) => {
                    // The Bar pill covers both orientations (bar = vertical, barh = horizontal).
                    const active =
                      opt.value === 'bar'
                        ? builder.viz === 'bar' || builder.viz === 'barh'
                        : builder.viz === opt.value;
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setBuilder((prev) => ({ ...prev, viz: opt.value }))}
                        className={
                          active
                            ? 'rounded-full border border-cobalt bg-cobalt/10 px-3 py-1 text-sm font-medium text-cobalt'
                            : 'rounded-full border border-border px-3 py-1 text-sm text-muted-foreground hover:bg-muted'
                        }
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {selectedMetric?.output === 'series' && (builder.viz === 'bar' || builder.viz === 'barh') && (
              <div className="space-y-1.5">
                <span className="text-sm font-medium text-foreground">Orientation</span>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: 'bar', label: 'Vertical' },
                    { value: 'barh', label: 'Horizontal' },
                  ] as { value: DashboardViz; label: string }[]).map((o) => {
                    const active = builder.viz === o.value;
                    return (
                      <button
                        key={o.value}
                        type="button"
                        onClick={() => setBuilder((prev) => ({ ...prev, viz: o.value }))}
                        className={
                          active
                            ? 'rounded-full border border-cobalt bg-cobalt/10 px-3 py-1 text-sm font-medium text-cobalt'
                            : 'rounded-full border border-border px-3 py-1 text-sm text-muted-foreground hover:bg-muted'
                        }
                      >
                        {o.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {selectedMetric?.output === 'series' && CARTESIAN_VIZ.includes(builder.viz) && (
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="X axis label"
                  placeholder="optional"
                  value={builder.xAxisLabel}
                  onChange={(e) =>
                    setBuilder((prev) => ({ ...prev, xAxisLabel: e.target.value }))
                  }
                />
                <Input
                  label="Y axis label"
                  placeholder="optional"
                  value={builder.yAxisLabel}
                  onChange={(e) =>
                    setBuilder((prev) => ({ ...prev, yAxisLabel: e.target.value }))
                  }
                />
              </div>
            )}
            {scopedOptionsLoading && (
              <AlertBanner tone="info" size="sm" role="status" aria-live="polite">
                Loading columns and states for the selected workflow…
              </AlertBanner>
            )}
            {scopedOptionsError && (
              <AlertBanner
                tone="error"
                size="sm"
                role="alert"
                title="Couldn't load workflow options"
                actions={
                  <Button variant="secondary" size="sm" onClick={onRetryScopedOptions}>
                    Retry
                  </Button>
                }
              >
                {scopedOptionsError}
              </AlertBanner>
            )}
            {selectedMetric?.params.map((p) => {
              const onChange = (value: string) =>
                setBuilder((prev) => ({
                  ...prev,
                  filters: { ...prev.filters, [p.key]: value },
                }));
              const sourceOptions = p.source ? filterOptions[p.source] : null;
              if (sourceOptions) {
                return (
                  <Select
                    key={p.key}
                    label={p.label}
                    placeholder={sourceOptions.length ? 'All' : 'No data available yet'}
                    value={builder.filters[p.key] ?? ''}
                    options={[
                      { value: '', label: 'All' },
                      ...sourceOptions.map((o: DashboardFilterOption) => ({
                        value: o.value,
                        label: o.label,
                      })),
                    ]}
                    disabled={p.source === 'states' && (scopedOptionsLoading || !!scopedOptionsError)}
                    onChange={(e) => onChange(e.target.value)}
                  />
                );
              }
              const presets = NUMBER_PRESETS[p.key];
              if (presets) {
                return (
                  <Select
                    key={p.key}
                    label={p.label}
                    placeholder="Default"
                    value={builder.filters[p.key] ?? ''}
                    options={[{ value: '', label: 'Default' }, ...presets]}
                    onChange={(e) => onChange(e.target.value)}
                  />
                );
              }
              return (
                <Input
                  key={p.key}
                  label={p.label}
                  placeholder={p.type === 'number' ? 'number' : 'optional'}
                  value={builder.filters[p.key] ?? ''}
                  onChange={(e) => onChange(e.target.value)}
                />
              );
            })}
            {builder.kind === 'table' && selectedMetric?.output === 'rows' && selectedMetric.fields.length > 0 && (
              <>
                {fieldsScopeWarning && (
                  <AlertBanner tone="warning" size="sm">
                    Couldn't determine this workflow's custom fields. Only standard workflow
                    columns are available.
                  </AlertBanner>
                )}
                <ColumnOrderPicker
                  label="Columns to show"
                  columns={selectedMetric.fields}
                  value={builder.fields}
                  onChange={(next) => setBuilder((prev) => ({ ...prev, fields: next }))}
                />
              </>
            )}
            {/* State line selection for the multi-line state trend. Gated by key
                for now; generalize to a metric flag if more state-trend metrics appear. */}
            {selectedMetric?.key === 'transitions.by_state' && filterOptions.states.length > 0 && (
              <ColumnOrderPicker
                label="States to show (optional — empty shows all)"
                columns={filterOptions.states.map((s) => ({ key: s.value, label: s.label }))}
                value={builder.states}
                onChange={(next) => setBuilder((prev) => ({ ...prev, states: next }))}
              />
            )}
            {builder.kind === 'activity' && (
              <ColumnOrderPicker
                label="Categories to show (optional — empty shows all)"
                columns={METADATA_TYPE_OPTIONS}
                value={builder.metadataTypes}
                onChange={(next) => setBuilder((prev) => ({ ...prev, metadataTypes: next }))}
              />
            )}
          </>
        ) : (
          <>
            <Input
              label="Title"
              value={builder.title}
              onChange={(e) => setBuilder((prev) => ({ ...prev, title: e.target.value }))}
            />
            <Input
              label="Description (optional)"
              placeholder="What does this action do?"
              value={builder.description}
              onChange={(e) => setBuilder((prev) => ({ ...prev, description: e.target.value }))}
            />
            <Input
              label="Navigate to (route)"
              placeholder="/jobs"
              value={builder.href}
              onChange={(e) => setBuilder((prev) => ({ ...prev, href: e.target.value }))}
            />
            <IconPicker
              value={builder.icon}
              onChange={(next) => setBuilder((prev) => ({ ...prev, icon: next }))}
            />
          </>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onSubmit}
            disabled={
              scopedOptionsLoading || !!scopedOptionsError
                ? true
                : builder.kind === 'query'
                ? !builder.query?.source
                : builder.kind === 'embedded'
                  ? !builder.componentKey
                  : builder.kind === 'content'
                    ? builder.elements.length === 0
                    : builder.kind === 'button'
                      ? false
                      : !builder.metric
            }
          >
            {editingId ? 'Save changes' : 'Add'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
