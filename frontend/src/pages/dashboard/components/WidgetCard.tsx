import { createElement, useCallback, useLayoutEffect, useRef, type RefObject } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import {
  Button,
  Card,
  DashboardActivityList,
  DashboardChart,
  DashboardGauge,
  DashboardMultiSeriesChart,
  DashboardStat,
  DashboardTable,
  getWidgetIcon,
} from '../../../core/components';
import type { DashboardWidgetData, DashboardWidgetDef } from '../../../core/types';
import { cn } from '../../../lib/utils';
import { EmbeddedWidgetBoundary, getEmbeddedWidget } from '../lib/embeddedWidgets';

export interface WidgetCardProps {
  widget: DashboardWidgetDef;
  data?: DashboardWidgetData;
  editMode: boolean;
  autoHeight?: boolean;
  onAutoHeightChange?: (id: string, height: number | null) => void;
  onEdit: () => void;
  onRemove: () => void;
  onNavigate: (href: string) => void;
}

interface WidgetBodyProps {
  widget: DashboardWidgetDef;
  data?: DashboardWidgetData;
  autoHeight?: boolean;
}

function WidgetBody({ widget, data, autoHeight = false }: WidgetBodyProps) {
  // Embedded widgets render from the curated registry and fetch through their
  // own domain hooks — they never receive /dashboards/data payloads.
  if (widget.type === 'embedded') {
    const entry = getEmbeddedWidget(widget.componentKey);
    if (!entry) {
      return (
        <div className="text-sm text-destructive">
          Unknown embedded widget “{widget.componentKey ?? '?'}”.
        </div>
      );
    }
    return (
      <EmbeddedWidgetBoundary>
        {/* Keyed by config: some config values seed internal state (e.g. the
            initial entity-type filter), so an edit-save must remount. */}
        <div
          key={JSON.stringify(widget.componentConfig ?? {})}
          className={cn('widget-no-drag min-h-0', autoHeight ? 'h-auto' : 'h-full')}
        >
          {entry.render(widget.componentConfig ?? {}, { autoHeight })}
        </div>
      </EmbeddedWidgetBoundary>
    );
  }
  if (!data) {
    return <div className="text-sm text-muted-foreground">Loading…</div>;
  }
  if (data.kind === 'error') {
    return <div className="text-sm text-destructive">{data.error}</div>;
  }
  if (widget.type === 'stat' && data.kind === 'scalar') {
    return (
      <DashboardStat
        value={data.value}
        prevValue={data.prevValue}
        icon={widget.icon}
        subtitle={widget.subtitle}
      />
    );
  }
  if (widget.type === 'gauge' && data.kind === 'gauge') {
    return <DashboardGauge value={data.value} max={data.max} label={data.label} />;
  }
  if ((widget.type === 'table' || widget.type === 'query') && data.kind === 'rows') {
    return <DashboardTable columns={data.columns} rows={data.rows} />;
  }
  if ((widget.type === 'chart' || widget.type === 'query') && data.kind === 'series') {
    return (
      <DashboardChart
        viz={widget.viz ?? 'bar'}
        series={data.series}
        xLabel={widget.xAxisLabel}
        yLabel={widget.yAxisLabel}
      />
    );
  }
  if ((widget.type === 'chart' || widget.type === 'query') && data.kind === 'multiseries') {
    return <DashboardMultiSeriesChart points={data.points} series={data.series} />;
  }
  if (widget.type === 'activity' && data.kind === 'rows') {
    return <DashboardActivityList rows={data.rows} />;
  }
  return <div className="text-sm text-muted-foreground">No data</div>;
}

function supportsAutoHeight(widget: DashboardWidgetDef, data?: DashboardWidgetData): boolean {
  if (widget.type === 'embedded') {
    const entry = getEmbeddedWidget(widget.componentKey);
    return entry?.supportsAutoHeight?.(widget.componentConfig ?? {}) ?? false;
  }
  if (widget.type === 'chart' || widget.type === 'gauge') return false;
  if (
    widget.type === 'query' &&
    (!data || data.kind === 'series' || data.kind === 'multiseries' || data.kind === 'gauge')
  ) {
    return false;
  }
  return true;
}

function outerHeight(element: HTMLElement): number {
  const style = window.getComputedStyle(element);
  if (style.position === 'absolute' || style.position === 'fixed') return 0;
  return (
    element.getBoundingClientRect().height +
    Number.parseFloat(style.marginTop || '0') +
    Number.parseFloat(style.marginBottom || '0')
  );
}

function useWidgetAutoHeight(
  widgetId: string,
  enabled: boolean,
  rootRef: RefObject<HTMLElement | null>,
  bodyRef: RefObject<HTMLElement | null>,
  onAutoHeightChange?: (id: string, height: number | null) => void,
) {
  const measure = useCallback(() => {
    const root = rootRef.current;
    if (!enabled || !root || !onAutoHeightChange) return;

    const body = bodyRef.current;
    if (!body) {
      onAutoHeightChange(widgetId, root.scrollHeight);
      return;
    }

    const rootStyle = window.getComputedStyle(root);
    const rootChrome =
      Number.parseFloat(rootStyle.paddingTop || '0') +
      Number.parseFloat(rootStyle.paddingBottom || '0') +
      Number.parseFloat(rootStyle.borderTopWidth || '0') +
      Number.parseFloat(rootStyle.borderBottomWidth || '0');
    const bodyChildren = Array.from(body.children);
    let bodyNatural = bodyChildren.length > 0 ? 0 : body.scrollHeight;
    for (const child of bodyChildren) {
      if (child instanceof HTMLElement) {
        bodyNatural = Math.max(
          bodyNatural,
          child.scrollHeight,
          child.offsetHeight,
        );
      }
    }

    let naturalHeight = rootChrome;
    for (const child of Array.from(root.children)) {
      if (!(child instanceof HTMLElement)) continue;
      naturalHeight += child === body ? bodyNatural : outerHeight(child);
    }
    onAutoHeightChange(widgetId, naturalHeight);
  }, [bodyRef, enabled, onAutoHeightChange, rootRef, widgetId]);

  useLayoutEffect(() => {
    if (!onAutoHeightChange) return;
    if (!enabled) {
      onAutoHeightChange(widgetId, null);
      return;
    }

    measure();
    const animationFrame = window.requestAnimationFrame(measure);
    const root = rootRef.current;
    const body = bodyRef.current;
    const resizeObserver =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            window.requestAnimationFrame(measure);
          })
        : null;
    const mutationObserver =
      typeof MutationObserver !== 'undefined'
        ? new MutationObserver(() => {
            window.requestAnimationFrame(measure);
          })
        : null;

    if (root) {
      resizeObserver?.observe(root);
      mutationObserver?.observe(root, {
        attributes: true,
        characterData: true,
        childList: true,
        subtree: true,
      });
    }
    if (body) {
      resizeObserver?.observe(body);
      for (const child of Array.from(body.children)) {
        if (child instanceof HTMLElement) resizeObserver?.observe(child);
      }
    }

    return () => {
      window.cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
    };
  }, [enabled, measure, onAutoHeightChange, rootRef, bodyRef, widgetId]);
}

export function WidgetCard({
  widget,
  data,
  editMode,
  autoHeight = false,
  onAutoHeightChange,
  onEdit,
  onRemove,
  onNavigate,
}: WidgetCardProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const shouldAutoHeight = autoHeight && supportsAutoHeight(widget, data);
  useWidgetAutoHeight(widget.id, shouldAutoHeight, rootRef, bodyRef, onAutoHeightChange);

  if (widget.type === 'content') {
    const verticalAlign = widget.verticalAlign ?? 'top';
    const verticalJustify =
      verticalAlign === 'middle' ? 'justify-center' : verticalAlign === 'bottom' ? 'justify-end' : 'justify-start';
    return (
      <div ref={rootRef} className="relative flex h-full flex-col overflow-auto p-2">
        {/* Alignment lives on this inner wrapper, not the scroll container above:
            justify-center/end on an overflowing flex container is "unsafe" per the
            CSS box-alignment spec, so overflow can clip unreachable past the start
            edge. min-h-full centers/ends when content fits and falls back to
            top-aligned flow (no extra space to distribute) when it overflows. */}
        <div
          ref={bodyRef}
          className={cn('flex flex-col gap-2', !shouldAutoHeight && 'min-h-full', verticalJustify)}
        >
          {(widget.elements ?? []).map((el) => {
            const align = el.align ?? 'left';
            const textAlign =
              align === 'center' ? 'text-center' : align === 'right' ? 'text-right' : 'text-left';
            const justify =
              align === 'center' ? 'justify-center' : align === 'right' ? 'justify-end' : 'justify-start';
            if (el.kind === 'header') {
              return (
                <h2 key={el.id} className={`text-xl font-semibold text-foreground ${textAlign}`}>
                  {el.text}
                </h2>
              );
            }
            if (el.kind === 'text') {
              return (
                <p key={el.id} className={`text-sm text-muted-foreground ${textAlign}`}>
                  {el.text}
                </p>
              );
            }
            return (
              <div key={el.id} className={`flex ${justify}`}>
                <Button
                  variant="primary"
                  className="widget-no-drag"
                  onClick={() => {
                    if (!editMode) onNavigate(el.href ?? '/');
                  }}
                >
                  {el.text}
                </Button>
              </div>
            );
          })}
        </div>
        {editMode && (
          <div className="widget-no-drag absolute right-1 top-1 flex items-center gap-1">
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={onEdit}
              aria-label="Edit widget"
            >
              <Pencil className="h-4 w-4" strokeWidth={1.5} />
            </button>
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive"
              onClick={onRemove}
              aria-label="Remove widget"
            >
              <Trash2 className="h-4 w-4" strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>
    );
  }
  if (widget.type === 'button') {
    const Icon = getWidgetIcon(widget.icon);
    return (
      <Card
        ref={rootRef}
        className={cn(
          'flex h-full flex-col p-4',
          shouldAutoHeight ? 'overflow-auto' : 'overflow-hidden',
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-3">
            {Icon && (
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cobalt/10 text-cobalt">
                {createElement(Icon, { className: 'h-5 w-5', strokeWidth: 1.5 })}
              </span>
            )}
            <h3 className="text-sm font-semibold text-foreground">{widget.title}</h3>
          </div>
          {editMode && (
            <div className="widget-no-drag flex items-center gap-1">
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={onEdit}
                aria-label="Edit widget"
              >
                <Pencil className="h-4 w-4" strokeWidth={1.5} />
              </button>
              <button
                type="button"
                className="text-muted-foreground hover:text-destructive"
                onClick={onRemove}
                aria-label="Remove widget"
              >
                <Trash2 className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>
          )}
        </div>
        {widget.description && (
          <p className="mt-2 text-sm text-muted-foreground">{widget.description}</p>
        )}
        <div ref={bodyRef} className="widget-no-drag mt-auto pt-4">
          <Button
            variant="primary"
            className="w-full"
            onClick={() => {
              if (!editMode) onNavigate(widget.href ?? '/');
            }}
          >
            {widget.title}
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <Card
      ref={rootRef}
      className={cn(
        'flex h-full flex-col overflow-hidden p-4',
      )}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          {widget.href && !editMode ? (
            <button
              type="button"
              onClick={() => onNavigate(widget.href ?? '/')}
              className="widget-no-drag truncate text-left text-sm font-medium text-cobalt hover:underline"
            >
              {widget.title}
            </button>
          ) : (
            <h3 className="truncate text-sm font-medium text-foreground">{widget.title}</h3>
          )}
          {widget.description && (
            <p className="mt-0.5 text-xs text-muted-foreground">{widget.description}</p>
          )}
        </div>
        {editMode && (
          <div className="widget-no-drag flex items-center gap-1">
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={onEdit}
              aria-label="Edit widget"
            >
              <Pencil className="h-4 w-4" strokeWidth={1.5} />
            </button>
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive"
              onClick={onRemove}
              aria-label="Remove widget"
            >
              <Trash2 className="h-4 w-4" strokeWidth={1.5} />
            </button>
          </div>
        )}
      </div>
      <div
        ref={bodyRef}
        className={cn('min-h-0 min-w-0 flex-1', shouldAutoHeight && 'overflow-auto')}
      >
        <WidgetBody widget={widget} data={data} autoHeight={shouldAutoHeight} />
      </div>
    </Card>
  );
}
