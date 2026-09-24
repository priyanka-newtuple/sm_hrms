import { ListChecks, Shield, Trash2 } from "lucide-react";
import type { Transition } from "@/lib/state-machine/types";
import { edgePath, edgeMidpoint, NODE_W, NODE_H } from "../utils/canvasUtils";
import { Button } from '@/components/ui/button';

interface CanvasEdgeProps {
  transition: Transition;
  from: { x: number; y: number };
  to: { x: number; y: number };
  isTerminalReject: boolean;
  isActive: boolean;
  isHover: boolean;
  transitionIssues?: Record<string, "error" | "warning">;
  onSelect: () => void;
  onDelete: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

const PILL_W = 240;
const PILL_H = 36;

export function CanvasEdge({
  transition: t,
  from,
  to,
  isTerminalReject,
  isActive,
  isHover,
  transitionIssues,
  onSelect,
  onDelete,
  onMouseEnter,
  onMouseLeave,
}: CanvasEdgeProps) {
  const isSelfLoop = t.from === t.to_state;
  const path = edgePath(from, to, isSelfLoop);
  const { x: midX, y: midY } = edgeMidpoint(from, to, isSelfLoop);

  const stroke = isActive
    ? "var(--color-foreground)"
    : isTerminalReject
      ? "var(--diagram-edge-reject)"
      : "var(--diagram-edge)";
  const marker = isActive ? "cv-arrow-active" : isTerminalReject ? "cv-arrow-reject" : "cv-arrow";

  const labelText = t.label || t.trigger || t.key;
  const guardCount = t.guards?.length ?? 0;
  const taskCount = (t.pre_transition_tasks?.length ?? 0) + (t.post_transition_tasks?.length ?? 0);
  const tIssue = transitionIssues?.[t.key];

  return (
    <g
      className="pointer-events-auto"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* fat invisible hit area */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        className="cursor-pointer"
        onMouseDown={(e) => {
          e.stopPropagation();
          onSelect();
        }}
      />
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth={isActive ? 2.6 : isHover ? 2 : 1.6}
        markerEnd={`url(#${marker})`}
        opacity={isActive ? 1 : isHover ? 1 : 0.9}
      />
      <foreignObject
        x={midX - PILL_W / 2}
        y={midY - PILL_H / 2}
        width={PILL_W}
        height={PILL_H}
        className="overflow-visible"
      >
        <div
          className={`group/edge flex h-[36px] items-center justify-center gap-1 rounded-md border bg-card px-2 text-[11px] shadow-sm transition-colors ${
            isActive
              ? "border-foreground"
              : isHover
                ? "border-foreground/60"
                : tIssue === "error"
                  ? "border-destructive/50"
                  : tIssue === "warning"
                    ? "border-warning/60"
                    : "border-border"
          }`}
          onMouseDown={(e) => {
            e.stopPropagation();
            onSelect();
          }}
          role="button"
          title="Click to edit transition"
          style={{ cursor: "pointer" }}
        >
          <span className="truncate font-medium text-foreground">{labelText}</span>
          {guardCount > 0 && (
            <span
              className="inline-flex shrink-0 items-center gap-0.5 rounded bg-muted px-1 py-0.5 text-[9px] font-medium text-muted-foreground"
              title={`${guardCount} guard${guardCount === 1 ? "" : "s"}`}
            >
              <Shield className="h-2.5 w-2.5" />
              {guardCount}
            </span>
          )}
          {taskCount > 0 && (
            <span
              className="inline-flex shrink-0 items-center gap-0.5 rounded bg-muted px-1 py-0.5 text-[9px] font-medium text-muted-foreground"
              title={`${taskCount} task${taskCount === 1 ? "" : "s"}`}
            >
              <ListChecks className="h-2.5 w-2.5" />
              {taskCount}
            </span>
          )}
          <Button variant="ghost"
            className={`ml-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground transition-opacity hover:bg-destructive/10 hover:text-destructive ${
              isActive || isHover ? "opacity-100" : "opacity-0"
            }`}
            onMouseDown={(e) => {
              e.stopPropagation();
              e.preventDefault();
              onDelete();
            }}
            title="Delete transition"
            aria-label="Delete transition"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </foreignObject>
    </g>
  );
}

export function CanvasEdgeMarkers() {
  return (
    <defs>
      <marker
        id="cv-arrow"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--diagram-edge)" />
      </marker>
      <marker
        id="cv-arrow-reject"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--diagram-edge-reject)" />
      </marker>
      <marker
        id="cv-arrow-active"
        viewBox="0 0 10 10"
        refX="9"
        refY="5"
        markerWidth="8"
        markerHeight="8"
        orient="auto-start-reverse"
      >
        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-foreground)" />
      </marker>
    </defs>
  );
}

export function CanvasConnectLine({
  startX,
  startY,
  curX,
  curY,
}: {
  startX: number;
  startY: number;
  curX: number;
  curY: number;
}) {
  const path = edgePath(
    { x: startX - NODE_W, y: startY - NODE_H / 2 },
    { x: curX, y: curY - NODE_H / 2 },
  );
  return (
    <path
      d={path}
      fill="none"
      stroke="var(--color-foreground)"
      strokeDasharray="6 4"
      strokeWidth={1.8}
    />
  );
}
