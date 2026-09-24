import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, WheelEvent as ReactWheelEvent } from "react";
// ReactWheelEvent kept for onWheel signature compat
import { NODE_W, NODE_H, type NodePositions, type ConnectState } from "../utils/canvasUtils";

interface DragState {
  type: "node";
  name: string;
  startX: number;
  startY: number;
  origX: number;
  origY: number;
}

interface PanState {
  startX: number;
  startY: number;
  origTx: number;
  origTy: number;
}

interface UseCanvasInteractionParams {
  positions: NodePositions;
  effectivePositions: NodePositions;
  onPositionsChange: (next: NodePositions) => void;
  selectedStateName: string | null;
  selectedTransitionKey: string | null;
  onDeleteState: (name: string) => void;
  onDeleteTransition: (key: string) => void;
  onSelectState: (name: string | null) => void;
  onCreateTransition: (from: string, to: string) => void;
}

export function useCanvasInteraction({
  positions,
  effectivePositions,
  onPositionsChange,
  selectedStateName,
  selectedTransitionKey,
  onDeleteState,
  onDeleteTransition,
  onSelectState,
  onCreateTransition,
}: UseCanvasInteractionParams) {
  const [zoom, setZoom] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const panRef = useRef<PanState | null>(null);
  const [connect, setConnect] = useState<ConnectState | null>(null);
  const [hoverNode, setHoverNode] = useState<string | null>(null);
  const [hoverEdge, setHoverEdge] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        if (selectedTransitionKey) {
          e.preventDefault();
          onDeleteTransition(selectedTransitionKey);
        } else if (selectedStateName) {
          e.preventDefault();
          onDeleteState(selectedStateName);
        }
      } else if (e.key === "Escape") {
        onSelectState(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedStateName, selectedTransitionKey, onDeleteState, onDeleteTransition, onSelectState]);

  const screenToWorld = useCallback(
    (clientX: number, clientY: number) => {
      const rect = containerRef.current!.getBoundingClientRect();
      return {
        x: (clientX - rect.left - tx) / zoom,
        y: (clientY - rect.top - ty) / zoom,
      };
    },
    [tx, ty, zoom],
  );

  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (dragRef.current) {
        const d = dragRef.current;
        const dx = (e.clientX - d.startX) / zoom;
        const dy = (e.clientY - d.startY) / zoom;
        onPositionsChange({
          ...positions,
          [d.name]: { x: d.origX + dx, y: d.origY + dy },
        });
      } else if (panRef.current) {
        const p = panRef.current;
        setTx(p.origTx + (e.clientX - p.startX));
        setTy(p.origTy + (e.clientY - p.startY));
      } else if (connect) {
        const w = screenToWorld(e.clientX, e.clientY);
        setConnect({ ...connect, curX: w.x, curY: w.y });
      }
    },
    [positions, onPositionsChange, zoom, connect, screenToWorld],
  );

  const onMouseUp = useCallback(
    (e: MouseEvent) => {
      if (connect) {
        if (hoverNode && hoverNode !== connect.fromName) {
          onCreateTransition(connect.fromName, hoverNode);
        }
        setConnect(null);
      }
      dragRef.current = null;
      panRef.current = null;
      void e;
    },
    [connect, hoverNode, onCreateTransition],
  );

  useEffect(() => {
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [onMouseMove, onMouseUp]);

  const beginNodeDrag = (e: ReactMouseEvent, name: string) => {
    e.stopPropagation();
    const p = effectivePositions[name];
    dragRef.current = {
      type: "node",
      name,
      startX: e.clientX,
      startY: e.clientY,
      origX: p.x,
      origY: p.y,
    };
    onSelectState(name);
  };

  const beginConnect = (e: ReactMouseEvent, name: string) => {
    e.stopPropagation();
    const p = effectivePositions[name];
    const start = { x: p.x + NODE_W, y: p.y + NODE_H / 2 };
    setConnect({ fromName: name, startX: start.x, startY: start.y, curX: start.x, curY: start.y });
  };

  const beginPan = (e: ReactMouseEvent) => {
    if (e.button !== 0) return;
    panRef.current = { startX: e.clientX, startY: e.clientY, origTx: tx, origTy: ty };
    onSelectState(null);
  };

  // Native non-passive wheel listener — required to preventDefault on pinch-zoom
  const zoomRef = useRef(zoom);
  const txRef = useRef(tx);
  const tyRef = useRef(ty);
  zoomRef.current = zoom;
  txRef.current = tx;
  tyRef.current = ty;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const isPinch = e.ctrlKey || e.metaKey;
      if (isPinch) {
        const delta = -e.deltaY * 0.008;
        const newZoom = Math.min(2, Math.max(0.3, zoomRef.current * (1 + delta)));
        const rect = el.getBoundingClientRect();
        const cx = e.clientX - rect.left;
        const cy = e.clientY - rect.top;
        const k = newZoom / zoomRef.current;
        setTx(cx - k * (cx - txRef.current));
        setTy(cy - k * (cy - tyRef.current));
        setZoom(newZoom);
      } else {
        // two-finger pan
        setTx((v) => v - e.deltaX);
        setTy((v) => v - e.deltaY);
      }
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  // kept for API compat but unused (native handler above takes over)
  const onWheel = (_e: ReactWheelEvent) => {};

  const fitView = useCallback(() => {
    const xs = Object.values(effectivePositions).map((p) => p.x);
    const ys = Object.values(effectivePositions).map((p) => p.y);
    if (xs.length === 0) {
      setZoom(1);
      setTx(0);
      setTy(0);
      return;
    }
    const minX = Math.min(...xs) - 40;
    const minY = Math.min(...ys) - 40;
    const maxX = Math.max(...xs) + NODE_W + 40;
    const maxY = Math.max(...ys) + NODE_H + 40;
    const rect = containerRef.current!.getBoundingClientRect();
    const k = Math.min(rect.width / (maxX - minX), rect.height / (maxY - minY), 1.2);
    setZoom(k);
    setTx(-minX * k + (rect.width - (maxX - minX) * k) / 2);
    setTy(-minY * k + (rect.height - (maxY - minY) * k) / 2);
  }, [effectivePositions]);

  const resetView = useCallback(() => {
    setZoom(1);
    setTx(0);
    setTy(0);
  }, []);

  return {
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
  };
}
