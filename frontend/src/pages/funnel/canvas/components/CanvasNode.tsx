import { Pencil, Plus, Trash2 } from "lucide-react";
import type { StateNode } from "@/lib/state-machine/types";
import { nodeAccent, NODE_W, NODE_H, type ConnectState } from "../utils/canvasUtils";
import { Button } from '@/components/ui/button';

interface CanvasNodeProps {
  state: StateNode;
  position: { x: number; y: number };
  isActive: boolean;
  isHover: boolean;
  connect: ConnectState | null;
  stateIssues?: Record<string, "error" | "warning">;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onDragStart: (e: React.MouseEvent) => void;
  onConnectStart: (e: React.MouseEvent) => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function CanvasNode({
  state: s,
  position: p,
  isActive,
  isHover,
  connect,
  stateIssues,
  onMouseEnter,
  onMouseLeave,
  onDragStart,
  onConnectStart,
  onEdit,
  onDelete,
}: CanvasNodeProps) {
  const accent = nodeAccent(s);
  const isDropTarget = connect !== null && isHover && connect.fromName !== s.name;

  return (
    <div
      className="absolute select-none"
      style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div
        className="group relative h-full w-full cursor-grab rounded-xl border bg-card shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing"
        style={{
          borderColor: isActive ? "var(--color-foreground)" : accent.stroke,
          borderWidth: isActive ? 2 : 1.4,
          background: accent.bg,
        }}
        onMouseDown={onDragStart}
      >
        <div className="flex h-full flex-col justify-between p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="truncate font-mono text-[13px] font-semibold text-foreground">
              {s.name}
            </div>
            {accent.label && (
              <span
                className="rounded-sm px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider"
                style={{ color: accent.stroke, background: "var(--color-card)" }}
              >
                {accent.label}
              </span>
            )}
          </div>
          <div className="line-clamp-2 text-[11px] text-muted-foreground">
            {s.description || "No description"}
          </div>
        </div>

        {/* Left handle (target) */}
        <div
          className="absolute -left-1.5 top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 bg-background"
          style={{ borderColor: accent.stroke }}
        />

        {/* Right handle (source) */}
        <div
          className="absolute -right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 cursor-crosshair items-center justify-center rounded-full border-2 bg-background opacity-70 transition-opacity hover:opacity-100"
          style={{ borderColor: accent.stroke }}
          onMouseDown={onConnectStart}
          title="Drag to another state to create a transition"
        >
          <Plus className="h-2.5 w-2.5" style={{ color: accent.stroke }} />
        </div>

        {/* Drop target ring */}
        {isDropTarget && (
          <div className="pointer-events-none absolute inset-0 rounded-xl ring-2 ring-foreground" />
        )}

        {/* Quick actions on hover/active */}
        {(isHover || isActive) && !connect && (
          <div className="absolute -top-3 right-2 flex items-center gap-0.5 rounded-md border border-border bg-card px-1 py-0.5 shadow-sm">
            <Button
              variant="ghost-action"
              size="icon-xs"
              className="text-muted-foreground hover:bg-accent hover:text-foreground"
              title="Edit state"
              onMouseDown={(e) => {
                e.stopPropagation();
                onEdit();
              }}
            >
              <Pencil className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost-danger"
              size="icon-xs"
              className="text-muted-foreground"
              title="Delete state"
              onMouseDown={(e) => {
                e.stopPropagation();
                onDelete();
              }}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        )}

        {/* Issue indicator dot */}
        {stateIssues?.[s.name] && (
          <div
            className={`pointer-events-none absolute -right-1 -top-1 h-3 w-3 rounded-full border-2 border-card ${
              stateIssues[s.name] === "error" ? "bg-destructive" : "bg-warning"
            }`}
          />
        )}
      </div>
    </div>
  );
}
