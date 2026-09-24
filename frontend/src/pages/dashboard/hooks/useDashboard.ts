import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { type Layout } from 'react-grid-layout';
import { dashboards } from '../../../core/services/api';
import type {
  DashboardConfig,
  DashboardDataItem,
  DashboardFilterOptionsResponse,
  DashboardMetricRead,
  DashboardWidgetData,
  DashboardWidgetDef,
} from '../../../core/types';
import type { TimeFilterValue } from '../../../core/components';
import { useGlobalEntityFilter } from '../../../core/contexts/GlobalEntityFilterContext';
import { EMPTY_FILTER_OPTIONS, GRID_COLS, GRID_MARGIN, LEGACY_GRID_SCALE, ROW_HEIGHT } from '../lib/constants';

export interface UseDashboardReturn {
  config: DashboardConfig | null;
  setConfig: React.Dispatch<React.SetStateAction<DashboardConfig | null>>;
  metrics: DashboardMetricRead[];
  filterOptions: DashboardFilterOptionsResponse;
  data: Record<string, DashboardWidgetData>;
  loading: boolean;
  error: string | null;
  editMode: boolean;
  saving: boolean;
  widgets: DashboardWidgetDef[];
  layout: Layout;
  time: TimeFilterValue;
  setEditMode: (v: boolean) => void;
  setTime: (v: TimeFilterValue) => void;
  handleLayoutChange: (current: Layout) => void;
  handleWidgetAutoHeightChange: (id: string, height: number | null) => void;
  removeWidget: (id: string) => void;
  saveLayout: () => Promise<void>;
  load: () => Promise<void>;
}

function rowsForContentHeight(height: number, minRows: number, maxRows: number): number {
  const [, marginY] = GRID_MARGIN;
  const rows = Math.ceil((height + marginY) / (ROW_HEIGHT + marginY));
  const floor = Math.min(minRows, maxRows);
  return Math.max(floor, Math.min(maxRows, rows));
}

function minRowsForWidget(widget: DashboardWidgetDef): number {
  if (widget.type === 'content') return 1;
  return 2;
}

export function useDashboard(enabled: boolean): UseDashboardReturn {
  const { activeAnchorEntityId } = useGlobalEntityFilter();
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetricRead[]>([]);
  const [filterOptions, setFilterOptions] = useState<DashboardFilterOptionsResponse>(
    EMPTY_FILTER_OPTIONS,
  );
  const [data, setData] = useState<Record<string, DashboardWidgetData>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [time, setTime] = useState<TimeFilterValue>({});
  const [autoHeights, setAutoHeights] = useState<Record<string, number>>({});
  // ponytail: ref so load/saveLayout always hydrate with current time without time in their deps
  const timeRef = useRef(time);
  useEffect(() => { timeRef.current = time; }, [time]);

  const hydrate = useCallback(
    async (nextWidgets: DashboardWidgetDef[], timeValue: TimeFilterValue) => {
      const items: DashboardDataItem[] = nextWidgets
        .filter((w) => w.metric || w.query)
        .map((w) =>
          w.query
            ? { widget_id: w.id, query: w.query, filters: { ...(w.filters ?? {}), ...timeValue } }
            : {
                widget_id: w.id,
                metric: w.metric as string,
                filters: { ...(w.filters ?? {}), ...timeValue },
              },
        );
      if (items.length === 0) {
        setData({});
        return;
      }
      const res = await dashboards.data({
        items,
        anchor_entity_id: activeAnchorEntityId,
      });
      setData(res.results);
    },
    [activeAnchorEntityId],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [def, metricsRes, optionsRes] = await Promise.all([
        dashboards.get('primary'),
        dashboards.metrics(),
        dashboards.filterOptions(),
      ]);
      const cfg = (def.config as unknown as DashboardConfig) ?? { widgets: [] };
      const rawWidgets = Array.isArray(cfg.widgets) ? cfg.widgets : [];
      // Migrate legacy 12-col layouts to the 60-col grid (x/w ×5). Idempotent:
      // only rescales when the stored config isn't already at GRID_COLS.
      const nextWidgets =
        cfg.cols === GRID_COLS
          ? rawWidgets
          : rawWidgets.map((w) => ({
              ...w,
              layout: {
                ...w.layout,
                x: w.layout.x * LEGACY_GRID_SCALE,
                w: w.layout.w * LEGACY_GRID_SCALE,
              },
            }));
      setConfig({ ...cfg, cols: GRID_COLS, widgets: nextWidgets });
      setMetrics(metricsRes.metrics);
      setFilterOptions(optionsRes);
      await hydrate(nextWidgets, timeRef.current);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [hydrate]);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);

  // Re-fetch all widgets when the global time filter changes.
  useEffect(() => {
    if (!enabled || !config) return;
    void hydrate(config.widgets, time);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [time, activeAnchorEntityId]);

  const widgets = useMemo(() => config?.widgets ?? [], [config]);

  useEffect(() => {
    setAutoHeights({});
  }, [widgets, data, editMode]);

  const layout = useMemo<Layout>(
    () =>
      widgets.map((w) => ({
        i: w.id,
        x: w.layout.x,
        y: w.layout.y,
        w: w.layout.w,
        h:
          !editMode && autoHeights[w.id] != null
            ? rowsForContentHeight(autoHeights[w.id], minRowsForWidget(w), w.layout.h)
            : w.layout.h,
        minW: LEGACY_GRID_SCALE * 2, // 10/60 = 1/6, so ≤6 across
        minH: editMode ? 2 : minRowsForWidget(w),
      })),
    [autoHeights, editMode, widgets],
  );

  const handleWidgetAutoHeightChange = useCallback((id: string, height: number | null) => {
    setAutoHeights((prev) => {
      if (height == null) {
        if (!(id in prev)) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      }
      const nextHeight = Math.ceil(height);
      if (Math.abs((prev[id] ?? 0) - nextHeight) < 2) return prev;
      return { ...prev, [id]: nextHeight };
    });
  }, []);

  const handleLayoutChange = useCallback(
    (current: Layout) => {
      if (!editMode) return;
      setConfig((prev) => {
        if (!prev) return prev;
        const byId = new Map(current.map((l) => [l.i, l]));
        return {
          ...prev,
          widgets: prev.widgets.map((w) => {
            const l = byId.get(w.id);
            return l ? { ...w, layout: { x: l.x, y: l.y, w: l.w, h: l.h } } : w;
          }),
        };
      });
    },
    [editMode],
  );

  const removeWidget = useCallback((id: string) => {
    setConfig((prev) =>
      prev ? { ...prev, widgets: prev.widgets.filter((w) => w.id !== id) } : prev,
    );
  }, []);

  const saveLayout = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    try {
      await dashboards.update('primary', {
        config: config as unknown as Record<string, unknown>,
      });
      setEditMode(false);
      await hydrate(config.widgets, timeRef.current);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save dashboard');
    } finally {
      setSaving(false);
    }
  }, [config, hydrate]);

  return {
    config,
    setConfig,
    metrics,
    filterOptions,
    data,
    loading,
    error,
    editMode,
    saving,
    widgets,
    layout,
    time,
    setEditMode,
    setTime,
    handleLayoutChange,
    handleWidgetAutoHeightChange,
    removeWidget,
    saveLayout,
    load,
  };
}
