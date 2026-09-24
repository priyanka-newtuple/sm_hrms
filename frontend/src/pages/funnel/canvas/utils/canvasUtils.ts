import type { CSSProperties } from "react";
import type { StateMachineDefinition, StateNode } from "@/lib/state-machine/types";

export type NodePositions = Record<string, { x: number; y: number }>;
export type CanvasStyle = CSSProperties & Record<`--${string}`, string>;

export interface ConnectState {
  fromName: string;
  startX: number;
  startY: number;
  curX: number;
  curY: number;
}

export const NODE_W = 200;
export const NODE_H = 84;

export const canvasThemeVars: CanvasStyle = {
  "--diagram-edge": "color-mix(in oklch, var(--foreground) 58%, var(--background))",
  "--diagram-edge-reject": "var(--destructive)",
  "--state-default": "color-mix(in oklch, var(--foreground) 32%, var(--border))",
  "--state-default-bg": "var(--card)",
  "--state-initial": "var(--primary)",
  "--state-initial-bg": "color-mix(in oklch, var(--primary) 12%, var(--card))",
  "--state-terminal-success": "oklch(0.54 0.16 145)",
  "--state-terminal-success-bg": "color-mix(in oklch, oklch(0.54 0.16 145) 12%, var(--card))",
  "--state-terminal-fail": "var(--destructive)",
  "--state-terminal-fail-bg": "color-mix(in oklch, var(--destructive) 12%, var(--card))",
};

function stateOrder(state: StateNode, fallback: number): number {
  return state.order ?? fallback;
}

export function autoLayout(def: StateMachineDefinition): NodePositions {
  const positions: NodePositions = {};
  const states = [...def.states].sort((a, b) => stateOrder(a, 0) - stateOrder(b, 0));
  if (states.length === 0) return positions;

  const adj = new Map<string, string[]>();
  states.forEach((s) => adj.set(s.name, []));
  for (const t of def.transitions) adj.get(t.from)?.push(t.to_state);

  const initial =
    states.find((s) => s.name === def.initial_state) ??
    states.find((s) => s.tags?.includes("initial")) ??
    states[0];

  const layer = new Map<string, number>();
  layer.set(initial.name, 0);
  const queue = [initial.name];
  while (queue.length) {
    const cur = queue.shift()!;
    const curL = layer.get(cur)!;
    for (const next of adj.get(cur) ?? []) {
      if (next === cur) continue;
      const candidate = curL + 1;
      if (!layer.has(next)) {
        layer.set(next, candidate);
        queue.push(next);
      }
    }
  }
  states.forEach((s, i) => {
    if (!layer.has(s.name)) layer.set(s.name, Math.max(0, i));
  });

  const byLayer = new Map<number, string[]>();
  for (const s of states) {
    const l = layer.get(s.name)!;
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l)!.push(s.name);
  }

  const COL_GAP = 120;
  const ROW_GAP = 50;
  const layers = [...byLayer.keys()].sort((a, b) => a - b);
  const maxRows = Math.max(...[...byLayer.values()].map((l) => l.length));
  const totalH = maxRows * NODE_H + (maxRows - 1) * ROW_GAP;

  layers.forEach((l, colIdx) => {
    const list = byLayer.get(l)!;
    list.sort((a, b) => {
      const sa = states.find((s) => s.name === a)!;
      const sb = states.find((s) => s.name === b)!;
      const ta = sa.tags?.includes("terminal") ? 1 : 0;
      const tb = sb.tags?.includes("terminal") ? 1 : 0;
      return ta - tb || stateOrder(sa, 0) - stateOrder(sb, 0);
    });
    const colH = list.length * NODE_H + (list.length - 1) * ROW_GAP;
    const startY = (totalH - colH) / 2;
    list.forEach((name, rowIdx) => {
      positions[name] = {
        x: 80 + colIdx * (NODE_W + COL_GAP),
        y: 80 + startY + rowIdx * (NODE_H + ROW_GAP),
      };
    });
  });

  return positions;
}

export function nodeAccent(s: StateNode) {
  if (s.tags?.includes("initial"))
    return { stroke: "var(--state-initial)", bg: "var(--state-initial-bg)", label: "TRIGGER" };
  if (s.tags?.includes("terminal")) {
    const fail = /reject|fail|cancel/i.test(s.name);
    return fail
      ? { stroke: "var(--state-terminal-fail)", bg: "var(--state-terminal-fail-bg)", label: "END" }
      : {
          stroke: "var(--state-terminal-success)",
          bg: "var(--state-terminal-success-bg)",
          label: "END",
        };
  }
  return { stroke: "var(--state-default)", bg: "var(--state-default-bg)", label: null };
}

export function edgePath(
  from: { x: number; y: number },
  to: { x: number; y: number },
  selfLoop = false,
): string {
  const x1 = from.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_H / 2;
  if (selfLoop) {
    const cx = from.x + NODE_W + 60;
    return `M ${x1} ${y1 - 10} C ${cx} ${y1 - 60}, ${cx} ${y1 + 60}, ${x1} ${y1 + 10}`;
  }
  if (x2 <= x1) {
    const midY = Math.max(y1, y2) + 90;
    return `M ${x1} ${y1} C ${x1 + 80} ${midY}, ${x2 - 80} ${midY}, ${x2} ${y2}`;
  }
  const cx = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`;
}

export function edgeMidpoint(
  from: { x: number; y: number },
  to: { x: number; y: number },
  selfLoop = false,
): { x: number; y: number } {
  const x1 = from.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_H / 2;
  if (selfLoop) {
    return { x: x1 + 45, y: y1 };
  }
  if (x2 <= x1) {
    const mc = Math.max(y1, y2) + 90;
    return { x: (x1 + x2) / 2, y: 0.125 * y1 + 0.75 * mc + 0.125 * y2 };
  }
  return { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
}
