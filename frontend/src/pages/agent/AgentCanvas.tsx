import { Component, useEffect, useRef, useState, type ReactNode } from 'react';
import { LayoutGrid } from 'lucide-react';
import { UIResourceRenderer } from '@mcp-ui/client';
import { Skeleton } from '@/components/ui/skeleton';
import EmptyState from '@/core/components/EmptyState';
import { useAgent } from '@/core/agent';
import { canvasRegistry } from './canvasRegistry';
import { useCanvasItems, type CanvasItem } from './useAgentCanvas';

/**
 * Isolates a single canvas item's render. Item props come from the model's tool
 * output and aren't schema-validated, so a malformed payload could throw during
 * render; without this boundary one bad item would crash the whole app instead of
 * just its tile. (Mirrors EmbeddedWidgetBoundary in the dashboard.)
 */
class CanvasItemBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error('Agent canvas item failed to render:', error);
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="rounded-xl border border-dashed border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          This item couldn't be rendered.
        </div>
      );
    }
    return this.props.children;
  }
}

/** Renders a single canvas item — an mcp-ui resource or a named component. */
function CanvasItemView({ item }: { item: CanvasItem }) {
  if (item.kind === 'resource') {
    return (
      <UIResourceRenderer
        resource={item.resource}
        onUIAction={async () => {
          /* prototype: UI actions from the resource are not wired back yet */
        }}
      />
    );
  }
  const Component = canvasRegistry[item.component];
  if (!Component) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        Unknown component "{item.component}".
      </div>
    );
  }
  return <Component {...item.props} />;
}

interface ItemLayout {
  /** Grid column span on md+ (the arranger: big views full-width, tiles compact). */
  span: string;
  /** Fixed-height class when the component needs a bounded box; '' otherwise. */
  sizeClass: string;
  /** True → the component fills a fixed-height box; false → natural height. */
  fixed: boolean;
}

/** The "arranger": decide where/how big each rendered component sits, so tiles
 *  group compactly and large views take full width — the basis for future
 *  drag-to-rearrange. */
function layoutFor(item: CanvasItem): ItemLayout {
  if (item.kind === 'resource') return { span: 'md:col-span-2', sizeClass: '', fixed: false };
  const c = item.component;
  if (c === 'pipeline_board' || c === 'pipeline_list' || c === 'pipeline_calendar') {
    return { span: 'md:col-span-2', sizeClass: 'h-[70vh]', fixed: true };
  }
  if (c === 'dashboard' || c === 'entity_table') {
    return { span: 'md:col-span-2', sizeClass: '', fixed: false };
  }
  if (c === 'stat_tile') return { span: 'md:col-span-1', sizeClass: 'h-44', fixed: true };
  if (c === 'dashboard_widget') {
    const type = (item.props as { def?: { type?: string } }).def?.type;
    return type === 'stat' || type === 'gauge'
      ? { span: 'md:col-span-1', sizeClass: 'h-44', fixed: true }
      : { span: 'md:col-span-1', sizeClass: 'h-80', fixed: true };
  }
  return { span: 'md:col-span-2', sizeClass: '', fixed: false };
}

function autoSkeletonHeight(item: CanvasItem): string {
  if (item.kind === 'component' && item.component === 'dashboard') return 'h-96';
  return 'h-40';
}

/** Wraps each item so it "builds" in: a brief staggered skeleton, then the real
 *  component fades/slides in. A freshly rendered item is briefly highlighted. */
function CanvasItemShell({
  item,
  index,
  highlighted,
  registerRef,
}: {
  item: CanvasItem;
  index: number;
  highlighted: boolean;
  registerRef: (id: string, el: HTMLDivElement | null) => void;
}) {
  const [ready, setReady] = useState(false);
  const layout = layoutFor(item);
  useEffect(() => {
    const delay = Math.min(index * 120, 600);
    const t = setTimeout(() => setReady(true), delay);
    return () => clearTimeout(t);
  }, [index]);

  return (
    <div
      ref={(el) => registerRef(item.id, el)}
      className={[
        layout.span,
        'scroll-mt-4 rounded-xl p-1 transition-all duration-1000',
        layout.fixed ? `flex flex-col ${layout.sizeClass}` : '',
        highlighted ? 'bg-cobalt/5 ring-2 ring-cobalt/40 ring-offset-2 ring-offset-background' : 'ring-0',
      ].join(' ')}
    >
      {item.title && (
        <p className="mb-1.5 shrink-0 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {item.title}
        </p>
      )}
      {ready ? (
        <div
          className={`animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out ${
            layout.fixed ? 'min-h-0 flex-1' : ''
          }`}
        >
          <CanvasItemBoundary>
            <CanvasItemView item={item} />
          </CanvasItemBoundary>
        </div>
      ) : (
        <Skeleton className={`w-full rounded-xl ${layout.fixed ? 'flex-1' : autoSkeletonHeight(item)}`} />
      )}
    </div>
  );
}

/** The right-hand "Body" canvas: a pure projection of the active conversation's
 *  tool calls — the app's real components render on the fly and rebuild when a
 *  past conversation is reopened. */
export default function AgentCanvas() {
  const { currentThread } = useAgent();
  const items = useCanvasItems(currentThread);

  const scrollRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const registerRef = (id: string, el: HTMLDivElement | null) => {
    if (el) itemRefs.current.set(id, el);
    else itemRefs.current.delete(id);
  };

  const seen = useRef<{ threadId?: string; ids: Set<string> }>({ ids: new Set() });
  const [highlightId, setHighlightId] = useState<string | null>(null);

  // When a genuinely new item is rendered live (not on thread switch/restore),
  // scroll it into view and flash a highlight.
  useEffect(() => {
    const threadId = currentThread?.id;
    const ids = items.map((i) => i.id);
    const prev = seen.current;

    if (prev.threadId !== threadId) {
      seen.current = { threadId, ids: new Set(ids) };
      return;
    }
    const fresh = ids.filter((id) => !prev.ids.has(id));
    seen.current = { threadId, ids: new Set(ids) };
    if (fresh.length === 0) return;

    const newest = fresh[fresh.length - 1];
    setHighlightId(newest);
    requestAnimationFrame(() => {
      itemRefs.current.get(newest)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    const t = setTimeout(() => setHighlightId(null), 1800);
    return () => clearTimeout(t);
  }, [items, currentThread?.id]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-5 py-3 text-sm font-medium text-foreground">
        <LayoutGrid className="h-4 w-4 text-muted-foreground" />
        Canvas
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto p-5">
        {items.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              surface="plain"
              title="Nothing rendered yet"
              description="Ask the agent to show a board, a table, or the dashboard — results render here as interactive components."
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
            {items.map((item, index) => (
              <CanvasItemShell
                key={item.id}
                item={item}
                index={index}
                highlighted={highlightId === item.id}
                registerRef={registerRef}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
