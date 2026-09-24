import { useNavigate } from 'react-router-dom';
import { Responsive, useContainerWidth } from 'react-grid-layout';
import { LayoutGrid, Pencil, Plus, RefreshCw, Save } from 'lucide-react';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import { AccessDenied, Badge, Button, DashboardTimeFilter, EmptyState } from '../../core/components';
import { usePermissions } from '../../core/hooks/usePermissions';
import { useAppLabels } from '../../shared/hooks';
import { GRID_COLS, GRID_MARGIN, ROW_HEIGHT } from './lib/constants';
import { useDashboard } from './hooks/useDashboard';
import { useWidgetBuilder } from './hooks/useWidgetBuilder';
import { WidgetCard } from './components/WidgetCard';
import { WidgetBuilderModal } from './components/WidgetBuilderModal';

export default function DashboardPage() {
  const { hasPermission, loading: permsLoading } = usePermissions();
  const navigate = useNavigate();
  const { width, containerRef } = useContainerWidth();

  const appLabels = useAppLabels();
  const canRead = hasPermission('dashboard:read');
  const canWrite = hasPermission('dashboard:write');

  const {
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
    handleLayoutChange,
    handleWidgetAutoHeightChange,
    removeWidget,
    saveLayout,
    load,
    setTime,
  } = useDashboard(canRead);

  const {
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
  } = useWidgetBuilder(metrics, filterOptions, setConfig);

  if (permsLoading) {
    return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  }
  if (!canRead) {
    return <AccessDenied message="You don't have permission to view the dashboard." />;
  }

  return (
    <div className="min-w-0 p-6">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LayoutGrid className="h-6 w-6 text-primary" strokeWidth={1.5} />
          <h1 className="text-xl font-semibold text-foreground">{appLabels.dashboard}</h1>
          {editMode && <Badge variant="warning">Editing</Badge>}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" strokeWidth={1.5} />
            Refresh
          </Button>
          {canWrite && !editMode && (
            <Button variant="secondary" size="sm" onClick={() => setEditMode(true)}>
              <Pencil className="h-4 w-4" strokeWidth={1.5} />
              Edit
            </Button>
          )}
          {canWrite && editMode && (
            <>
              <Button variant="secondary" size="sm" onClick={openBuilder}>
                <Plus className="h-4 w-4" strokeWidth={1.5} />
                Add widget
              </Button>
              <Button variant="primary" size="sm" onClick={() => void saveLayout()} disabled={saving}>
                <Save className="h-4 w-4" strokeWidth={1.5} />
                {saving ? 'Saving…' : 'Save'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void load()}>
                Cancel
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2">
        <DashboardTimeFilter value={time} onChange={setTime} />
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* The grid container ref must stay mounted across loading/empty states.
          useContainerWidth only attaches its ResizeObserver on mount; if this
          element is unmounted while loading, the observer never attaches and the
          width sticks at the 1280px default, overflowing the viewport. */}
      <div ref={containerRef} className="min-w-0">
        {loading ? (
          <div className="p-8 text-sm text-muted-foreground">Loading dashboard…</div>
        ) : widgets.length === 0 ? (
          <EmptyState
            icon={<LayoutGrid className="h-10 w-10" strokeWidth={1.5} />}
            title="No widgets yet"
            description={
              canWrite
                ? 'Switch to Edit mode and add your first widget.'
                : 'This dashboard has no widgets yet.'
            }
            action={
              canWrite ? (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setEditMode(true);
                    openBuilder();
                  }}
                >
                  <Plus className="h-4 w-4" strokeWidth={1.5} />
                  Add widget
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Responsive
            className="layout"
            width={width}
            layouts={{ lg: layout }}
            breakpoints={{ lg: 0 }}
            cols={{ lg: GRID_COLS }}
            rowHeight={ROW_HEIGHT}
            margin={GRID_MARGIN}
            dragConfig={{ enabled: editMode, cancel: '.widget-no-drag' }}
            resizeConfig={{ enabled: editMode }}
            onLayoutChange={handleLayoutChange}
          >
            {widgets.map((w) => (
              <div key={w.id}>
                <WidgetCard
                  widget={w}
                  data={data[w.id]}
                  editMode={editMode}
                  autoHeight={!editMode}
                  onAutoHeightChange={handleWidgetAutoHeightChange}
                  onEdit={() => openEditor(w)}
                  onRemove={() => removeWidget(w.id)}
                  onNavigate={(href) => navigate(href)}
                />
              </div>
            ))}
          </Responsive>
        )}
      </div>

      <WidgetBuilderModal
        open={builderOpen}
        onClose={closeBuilder}
        editingId={editingId}
        builder={builder}
        setBuilder={setBuilder}
        onPickKind={onPickKind}
        onPickMetric={onPickMetric}
        onSubmit={submitWidget}
        kindMetrics={kindMetrics}
        selectedMetric={selectedMetric}
        filterOptions={effectiveFilterOptions}
        fieldsScopeWarning={fieldsScopeWarning}
        scopedOptionsLoading={scopedOptionsLoading}
        scopedOptionsError={scopedOptionsError}
        onRetryScopedOptions={retryScopedOptions}
      />
    </div>
  );
}
