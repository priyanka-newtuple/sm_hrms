import { useCallback, useEffect, useState } from 'react';
import { dashboards } from '../../../core/services/api';
import type {
  DashboardConfig,
  DashboardFilterOptionsResponse,
  DashboardMetricFieldRead,
  DashboardMetricRead,
  DashboardWidgetDef,
} from '../../../core/types';
import {
  ACTIVITY_METRIC_KEY,
  type BuilderState,
  CARTESIAN_VIZ,
  EMPTY_BUILDER,
  KIND_OUTPUT,
  type WidgetKind,
} from '../lib/constants';
import {
  builderFromWidget,
  defaultLayoutForType,
  vizForOutput,
  widgetTypeForOutput,
} from '../lib/utils';
import { getEmbeddedWidget } from '../lib/embeddedWidgets';

export interface UseWidgetBuilderReturn {
  builderOpen: boolean;
  builder: BuilderState;
  editingId: string | null;
  selectedMetric: DashboardMetricRead | undefined;
  kindMetrics: DashboardMetricRead[];
  /**
   * Org-wide `filterOptions`, with `states` narrowed to the picked workflow's
   * own states once a specific one (not "All") is chosen. `workflows` /
   * `entity_types` / `event_types` are always the org-wide lists — those are
   * what the pickers choose *from*.
   */
  effectiveFilterOptions: DashboardFilterOptionsResponse;
  /**
   * True when the server couldn't scope "Columns to show" to the picked
   * workflow (its entity type failed to resolve) and fell back to listing
   * every field in the org — so the user isn't misled into thinking the list
   * is specific to this workflow when it silently isn't.
   */
  fieldsScopeWarning: boolean;
  scopedOptionsLoading: boolean;
  scopedOptionsError: string | null;
  retryScopedOptions: () => void;
  setBuilder: React.Dispatch<React.SetStateAction<BuilderState>>;
  openBuilder: () => void;
  openEditor: (widget: DashboardWidgetDef) => void;
  closeBuilder: () => void;
  onPickKind: (kind: WidgetKind) => void;
  onPickMetric: (key: string) => void;
  submitWidget: () => void;
}

export function useWidgetBuilder(
  metrics: DashboardMetricRead[],
  filterOptions: DashboardFilterOptionsResponse,
  setConfig: React.Dispatch<React.SetStateAction<DashboardConfig | null>>,
): UseWidgetBuilderReturn {
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builder, setBuilder] = useState<BuilderState>(EMPTY_BUILDER);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [fieldsRequest, setFieldsRequest] = useState<{
    workflowId: string;
    metric: string;
    status: 'loading' | 'ready' | 'error';
    fields: DashboardMetricFieldRead[];
    scoped: boolean;
    error: string | null;
  } | null>(null);
  const [statesRequest, setStatesRequest] = useState<{
    workflowId: string;
    metric: string;
    status: 'loading' | 'ready' | 'error';
    states: DashboardFilterOptionsResponse['states'];
    error: string | null;
  } | null>(null);
  const [scopedOptionsRetry, setScopedOptionsRetry] = useState(0);

  const rawSelectedMetric = metrics.find((m) => m.key === builder.metric);
  const workflowId = builder.filters.workflow_id || '';
  const needsScopedFields = builder.kind === 'table';
  const needsScopedStates = rawSelectedMetric?.params.some((p) => p.source === 'states') ?? false;

  const fieldsRequestMatches =
    workflowId &&
    fieldsRequest?.workflowId === workflowId &&
    fieldsRequest.metric === builder.metric
      ? fieldsRequest
      : null;
  const statesRequestMatches =
    workflowId &&
    statesRequest?.workflowId === workflowId &&
    statesRequest.metric === builder.metric
      ? statesRequest
      : null;
  const fieldsStatus =
    workflowId && needsScopedFields ? (fieldsRequestMatches?.status ?? 'loading') : 'idle';
  const statesStatus =
    workflowId && needsScopedStates ? (statesRequestMatches?.status ?? 'loading') : 'idle';
  const scopedFields = fieldsStatus === 'ready' ? (fieldsRequestMatches?.fields ?? []) : null;
  const scopedStates = statesStatus === 'ready' ? (statesRequestMatches?.states ?? []) : null;
  const fieldsScopeWarning =
    fieldsStatus === 'ready' && fieldsRequestMatches !== null && !fieldsRequestMatches.scoped;
  const scopedOptionsLoading = fieldsStatus === 'loading' || statesStatus === 'loading';
  const scopedOptionsError =
    (fieldsStatus === 'error' ? fieldsRequestMatches?.error : null) ||
    (statesStatus === 'error' ? statesRequestMatches?.error : null) ||
    null;

  const selectedMetric = rawSelectedMetric
    ? {
        ...rawSelectedMetric,
        // Once a workflow is selected, an unresolved request must never expose
        // the org-wide field catalog as though it belonged to that workflow.
        fields:
          workflowId && needsScopedFields ? (scopedFields ?? []) : rawSelectedMetric.fields,
      }
    : undefined;
  const effectiveFilterOptions: DashboardFilterOptionsResponse =
    workflowId && needsScopedStates
      ? { ...filterOptions, states: scopedStates ?? [] }
      : filterOptions;

  const retryScopedOptions = useCallback(() => {
    setScopedOptionsRetry((value) => value + 1);
  }, []);

  // Refetch the columns/states catalogs scoped to the picked workflow. Only
  // fires once a *specific* workflow (not "All") is chosen, and only for the
  // catalogs the current metric actually needs — otherwise the org-wide props
  // are used with no extra request. Reconciles rather than wipes: once scoped
  // data lands, previously-picked columns/states that no longer exist in the
  // new catalog are dropped, not the whole selection — switching workflows
  // shouldn't silently blow away a pick that's still valid.
  useEffect(() => {
    if (!workflowId) return;
    let cancelled = false;
    const metric = builder.metric;
    if (needsScopedFields) {
      setFieldsRequest({
        workflowId,
        metric,
        status: 'loading',
        fields: [],
        scoped: false,
        error: null,
      });
      void dashboards
        .metrics(workflowId)
        .then((res) => {
          if (cancelled) return;
          const metricFields = res.metrics.find((x) => x.key === metric)?.fields ?? [];
          // If the backend cannot resolve the workflow's entity type, retain
          // only stable built-in columns. Org-wide data.* fields are not safe
          // choices for a workflow-scoped widget.
          const fields = res.fields_scoped
            ? metricFields
            : metricFields.filter((field) => !field.key.startsWith('data.'));
          setFieldsRequest({
            workflowId,
            metric,
            status: 'ready',
            fields,
            scoped: res.fields_scoped,
            error: null,
          });
          const validKeys = new Set(fields.map((field) => field.key));
          setBuilder((prev) => {
            if (prev.metric !== metric || prev.filters.workflow_id !== workflowId) return prev;
            const pruned = prev.fields.filter((key) => validKeys.has(key));
            return pruned.length === prev.fields.length ? prev : { ...prev, fields: pruned };
          });
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          setFieldsRequest({
            workflowId,
            metric,
            status: 'error',
            fields: [],
            scoped: false,
            error: error instanceof Error ? error.message : 'Failed to load workflow columns',
          });
        });
    }
    if (needsScopedStates) {
      const stateFilterKeys =
        rawSelectedMetric?.params
          .filter((param) => param.source === 'states')
          .map((param) => param.key) ?? [];
      setStatesRequest({
        workflowId,
        metric,
        status: 'loading',
        states: [],
        error: null,
      });
      void dashboards
        .filterOptions(workflowId)
        .then((res) => {
          if (cancelled) return;
          setStatesRequest({
            workflowId,
            metric,
            status: 'ready',
            states: res.states,
            error: null,
          });
          const validKeys = new Set(res.states.map((state) => state.value));
          setBuilder((prev) => {
            if (prev.metric !== metric || prev.filters.workflow_id !== workflowId) return prev;
            const filters = { ...prev.filters };
            let changed = false;
            for (const key of stateFilterKeys) {
              const value = filters[key];
              if (value && !validKeys.has(value)) {
                delete filters[key];
                changed = true;
              }
            }
            const states = prev.states.filter((key) => validKeys.has(key));
            if (states.length !== prev.states.length) changed = true;
            return changed ? { ...prev, filters, states } : prev;
          });
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          setStatesRequest({
            workflowId,
            metric,
            status: 'error',
            states: [],
            error: error instanceof Error ? error.message : 'Failed to load workflow states',
          });
        });
    }
    return () => {
      cancelled = true;
    };
  }, [
    workflowId,
    needsScopedFields,
    needsScopedStates,
    builder.metric,
    rawSelectedMetric,
    scopedOptionsRetry,
  ]);

  const kindMetrics = ((): DashboardMetricRead[] => {
    if (
      builder.kind === 'button' ||
      builder.kind === 'query' ||
      builder.kind === 'embedded' ||
      builder.kind === 'content'
    )
      return [];
    if (builder.kind === 'chart') {
      return metrics.filter((m) => m.output === 'series' || m.output === 'multiseries');
    }
    if (builder.kind === 'activity') {
      return metrics.filter((m) => m.key === ACTIVITY_METRIC_KEY);
    }
    const output = KIND_OUTPUT[builder.kind];
    return metrics.filter((m) => m.output === output);
  })();

  const openBuilder = useCallback(() => {
    setBuilder(EMPTY_BUILDER);
    setEditingId(null);
    setBuilderOpen(true);
  }, []);

  const openEditor = useCallback((widget: DashboardWidgetDef) => {
    setBuilder(builderFromWidget(widget));
    setEditingId(widget.id);
    setBuilderOpen(true);
  }, []);

  const closeBuilder = useCallback(() => {
    setBuilderOpen(false);
    setEditingId(null);
  }, []);

  const onPickKind = useCallback((kind: WidgetKind) => {
    setBuilder((prev) => ({ ...EMPTY_BUILDER, kind, title: prev.title }));
  }, []);

  const onPickMetric = useCallback(
    (key: string) => {
      const m = metrics.find((x) => x.key === key);
      setBuilder((prev) => ({
        ...prev,
        metric: key,
        title: prev.title || (m?.label ?? ''),
        viz: m ? vizForOutput(m) : prev.viz,
        filters: {},
        fields: [],
        states: [],
        metadataTypes: [],
      }));
    },
    [metrics],
  );

  const submitWidget = useCallback(() => {
    setConfig((prev) => {
      if (!prev) return prev;
      const existing = editingId ? prev.widgets.find((w) => w.id === editingId) : undefined;
      const id = existing?.id ?? `w-${Date.now().toString(36)}`;
      const maxY = prev.widgets.reduce((acc, w) => Math.max(acc, w.layout.y + w.layout.h), 0);
      let widget: DashboardWidgetDef;
      if (builder.kind === 'query') {
        if (!builder.query || !builder.query.source) return prev;
        const queryWidget: DashboardWidgetDef = {
          id,
          type: 'query',
          title: builder.title || 'Query',
          query: builder.query,
          viz: builder.viz,
          layout: existing?.layout ?? { x: 0, y: maxY, ...defaultLayoutForType('chart') },
        };
        const queryWidgets = existing
          ? prev.widgets.map((w) => (w.id === existing.id ? queryWidget : w))
          : [...prev.widgets, queryWidget];
        return { ...prev, widgets: queryWidgets };
      }
      if (builder.kind === 'embedded') {
        const entry = getEmbeddedWidget(builder.componentKey);
        if (!entry) return prev;
        const embeddedWidget: DashboardWidgetDef = {
          id,
          type: 'embedded',
          title: builder.title || entry.label,
          componentKey: builder.componentKey,
          componentConfig: builder.componentConfig,
          layout: existing?.layout ?? { x: 0, y: maxY, ...entry.defaultLayout },
        };
        const embeddedWidgets = existing
          ? prev.widgets.map((w) => (w.id === existing.id ? embeddedWidget : w))
          : [...prev.widgets, embeddedWidget];
        return { ...prev, widgets: embeddedWidgets };
      }
      if (builder.kind === 'button') {
        widget = {
          id,
          type: 'button',
          title: builder.title || 'Action',
          href: builder.href || '/',
          ...(builder.description ? { description: builder.description } : {}),
          ...(builder.icon ? { icon: builder.icon } : {}),
          layout: existing?.layout ?? { x: 0, y: maxY, ...defaultLayoutForType('button') },
        };
      } else if (builder.kind === 'content') {
        if (builder.elements.length === 0) return prev;
        widget = {
          id,
          type: 'content',
          title: builder.title || 'Content',
          elements: builder.elements,
          verticalAlign: builder.verticalAlign,
          layout: existing?.layout ?? { x: 0, y: maxY, ...defaultLayoutForType('content') },
        };
      } else {
        const m = metrics.find((x) => x.key === builder.metric);
        if (!m) return prev;
        const type = builder.kind === 'activity' ? 'activity' : widgetTypeForOutput(m.output);
        const filters: Record<string, unknown> = Object.fromEntries(
          Object.entries(builder.filters).filter(([, v]) => v !== ''),
        );
        if (m.output === 'rows' && builder.fields.length > 0) {
          filters.fields = builder.fields;
        }
        if (m.output === 'multiseries' && builder.states.length > 0) {
          filters.states = builder.states;
        }
        if (builder.kind === 'activity' && builder.metadataTypes.length > 0) {
          filters.metadata_type = builder.metadataTypes;
        }
        const isCartesianChart = type === 'chart' && CARTESIAN_VIZ.includes(builder.viz);
        widget = {
          id,
          type,
          title: builder.title || m.label,
          metric: m.key,
          filters,
          viz: builder.viz,
          ...(builder.description ? { description: builder.description } : {}),
          ...(builder.href ? { href: builder.href } : {}),
          ...(type === 'stat' && builder.icon ? { icon: builder.icon } : {}),
          ...(builder.kind === 'stat' && builder.subtitle ? { subtitle: builder.subtitle } : {}),
          ...(isCartesianChart && builder.xAxisLabel ? { xAxisLabel: builder.xAxisLabel } : {}),
          ...(isCartesianChart && builder.yAxisLabel ? { yAxisLabel: builder.yAxisLabel } : {}),
          layout: existing?.layout ?? { x: 0, y: maxY, ...defaultLayoutForType(type) },
        };
      }
      const widgets = existing
        ? prev.widgets.map((w) => (w.id === id ? widget : w))
        : [...prev.widgets, widget];
      return { ...prev, widgets };
    });
    setBuilderOpen(false);
    setEditingId(null);
  }, [builder, metrics, editingId, setConfig]);

  return {
    builderOpen,
    builder,
    editingId,
    selectedMetric,
    kindMetrics,
    effectiveFilterOptions,
    fieldsScopeWarning,
    scopedOptionsLoading,
    scopedOptionsError,
    retryScopedOptions,
    setBuilder,
    openBuilder,
    openEditor,
    closeBuilder,
    onPickKind,
    onPickMetric,
    submitWidget,
  };
}
