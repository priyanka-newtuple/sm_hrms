import { useEffect, useMemo } from "react";
import type { StateMachineDefinition } from "@/lib/state-machine/types";
import { Minus, Maximize2, Locate, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  NODE_W,
  NODE_H,
  autoLayout,
  canvasThemeVars,
  type NodePositions,
  type ConnectState,
} from "./utils/canvasUtils";
import { useCanvasInteraction } from "./hooks/useCanvasInteraction";
import { CanvasNode } from "./components/CanvasNode";
import {
  CanvasEdge,
  CanvasEdgeMarkers,
  CanvasConnectLine,
} from "./components/CanvasEdge";

export type { NodePositions };

interface Props {
  definition: StateMachineDefinition;
  positions: NodePositions;
  onPositionsChange: (next: NodePositions) => void;
  selectedStateName: string | null;
  selectedTransitionKey: string | null;
  onSelectState: (name: string | null) => void;
  onEditState: (name: string) => void;
  onSelectTransition: (key: string | null) => void;
  onAddState: () => void;
  onCreateTransition: (from: string, to: string) => void;
  onDeleteState: (name: string) => void;
  onDeleteTransition: (key: string) => void;
  stateIssues?: Record<string, "error" | "warning">;
  transitionIssues?: Record<string, "error" | "warning">;
}

export function WorkflowCanvas({
  definition,
  positions,
  onPositionsChange,
  selectedStateName,
  selectedTransitionKey,
  onSelectState,
  onEditState,
  onSelectTransition,
  onAddState,
  onCreateTransition,
  onDeleteState,
  onDeleteTransition,
  stateIssues,
  transitionIssues,
}: Props) {
  const effectivePositions = useMemo<NodePositions>(() => {
    const out: NodePositions = { ...positions };
    const missing = definition.states.some((s) => !out[s.name]);
    if (missing) {
      const layoutPos = autoLayout(definition);
      for (const s of definition.states) {
        if (!out[s.name]) out[s.name] = layoutPos[s.name] ?? { x: 80, y: 80 };
      }
    }
    return out;
  }, [definition, positions]);

  // Sync newly-laid-out positions back so they persist
  useEffect(() => {
    const missingKeys = definition.states.filter((s) => !positions[s.name]).map((s) => s.name);
    if (missingKeys.length > 0) {
      const next = { ...positions };
      for (const k of missingKeys) next[k] = effectivePositions[k];
      onPositionsChange(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definition.states.length]);

  const {
    zoom,
    setZoom,
    tx,
    ty,
    containerRef,
    connect,
    hoverNode,
    setHoverNode,
    hoverEdge,
    setHoverEdge,
    beginNodeDrag,
    beginConnect,
    beginPan,
    onWheel,
    fitView,
    resetView,
  } = useCanvasInteraction({
    positions,
    effectivePositions,
    onPositionsChange,
    selectedStateName,
    selectedTransitionKey,
    onDeleteState,
    onDeleteTransition,
    onSelectState,
    onCreateTransition,
  });

  // Initial fit
  useEffect(() => {
    const id = requestAnimationFrame(() => fitView());
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const bounds = useMemo(() => {
    const xs = Object.values(effectivePositions).map((p) => p.x);
    const ys = Object.values(effectivePositions).map((p) => p.y);
    const w = Math.max(2400, (xs.length ? Math.max(...xs) : 0) + NODE_W + 400);
    const h = Math.max(1600, (ys.length ? Math.max(...ys) : 0) + NODE_H + 400);
    return { w, h };
  }, [effectivePositions]);

  return (
    <div
      ref={containerRef}
      className="canvas-grid relative h-full w-full overflow-hidden"
      onMouseDown={beginPan}
      onWheel={onWheel}
      style={{ ...canvasThemeVars, cursor: "default" }}
    >
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{ transform: `translate(${tx}px, ${ty}px) scale(${zoom})` }}
      >
        <svg
          width={bounds.w}
          height={bounds.h}
          className="pointer-events-none absolute left-0 top-0"
          overflow="visible"
        >
          <CanvasEdgeMarkers />

          {definition.transitions.map((t) => {
            const from = effectivePositions[t.from];
            const to = effectivePositions[t.to_state];
            if (!from || !to) return null;
            const toState = definition.states.find((s) => s.name === t.to_state);
            const isTerminalReject =
              !!toState?.tags?.includes("terminal") && /reject|fail|cancel/i.test(t.to_state);
            return (
              <CanvasEdge
                key={t.key}
                transition={t}
                from={from}
                to={to}
                isTerminalReject={isTerminalReject}
                isActive={selectedTransitionKey === t.key}
                isHover={hoverEdge === t.key}
                transitionIssues={transitionIssues}
                onSelect={() => onSelectTransition(t.key)}
                onDelete={() => onDeleteTransition(t.key)}
                onMouseEnter={() => setHoverEdge(t.key)}
                onMouseLeave={() => setHoverEdge((c) => (c === t.key ? null : c))}
              />
            );
          })}

          {connect && (
            <CanvasConnectLine
              startX={connect.startX}
              startY={connect.startY}
              curX={connect.curX}
              curY={connect.curY}
            />
          )}
        </svg>

        {definition.states.map((s) => {
          const p = effectivePositions[s.name];
          if (!p) return null;
          return (
            <CanvasNode
              key={s.name}
              state={s}
              position={p}
              isActive={selectedStateName === s.name}
              isHover={hoverNode === s.name}
              connect={connect as ConnectState | null}
              stateIssues={stateIssues}
              onMouseEnter={() => setHoverNode(s.name)}
              onMouseLeave={() => setHoverNode((cur) => (cur === s.name ? null : cur))}
              onDragStart={(e) => beginNodeDrag(e, s.name)}
              onConnectStart={(e) => beginConnect(e, s.name)}
              onEdit={() => onEditState(s.name)}
              onDelete={() => onDeleteState(s.name)}
            />
          );
        })}

        {definition.states.length === 0 && (
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
            <p className="text-sm text-muted-foreground">No states yet.</p>
            <Button variant="ghost" size="sm" className="mt-2" onClick={onAddState}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Add first state
            </Button>
          </div>
        )}
      </div>

      {/* Floating zoom controls */}
      <div className="absolute bottom-4 left-4 flex items-center gap-1 rounded-md border border-border bg-card/95 p-1 shadow-sm backdrop-blur">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setZoom((z) => Math.max(0.3, z - 0.1))}
        >
          <Minus className="h-3.5 w-3.5" />
        </Button>
        <span className="w-12 text-center font-mono text-[11px] text-muted-foreground">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setZoom((z) => Math.min(2, z + 0.1))}
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
        <div className="mx-1 h-5 w-px bg-border" />
        <Button variant="ghost" size="icon" onClick={fitView} title="Fit to view">
          <Maximize2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={resetView}
          title="Reset view"
        >
          <Locate className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
