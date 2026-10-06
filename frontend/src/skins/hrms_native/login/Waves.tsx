/**
 * Adapted from React Bits "Waves" (https://reactbits.dev, MIT + Commons Clause): a field of thin lines
 * drifting on Perlin noise that bend away from the pointer. Changes for HRMS: device-pixel-ratio
 * rendering, pauses while the tab is hidden, and a single still frame under reduced motion.
 */
import { useEffect, useRef } from 'react';

class Grad {
  x: number;
  y: number;
  constructor(x: number, y: number) { this.x = x; this.y = y; }
  dot2(x: number, y: number) { return this.x * x + this.y * y; }
}

const GRAD3 = [[1, 1], [-1, 1], [1, -1], [-1, -1], [1, 0], [-1, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [0, 1], [0, -1]].map(([x, y]) => new Grad(x, y));
const P = [151, 160, 137, 91, 90, 15, 131, 13, 201, 95, 96, 53, 194, 233, 7, 225, 140, 36, 103, 30, 69, 142, 8, 99, 37, 240, 21, 10, 23, 190, 6, 148, 247, 120, 234, 75, 0, 26, 197, 62, 94, 252, 219, 203, 117, 35, 11, 32, 57, 177, 33, 88, 237, 149, 56, 87, 174, 20, 125, 136, 171, 168, 68, 175, 74, 165, 71, 134, 139, 48, 27, 166, 77, 146, 158, 231, 83, 111, 229, 122, 60, 211, 133, 230, 220, 105, 92, 41, 55, 46, 245, 40, 244, 102, 143, 54, 65, 25, 63, 161, 1, 216, 80, 73, 209, 76, 132, 187, 208, 89, 18, 169, 200, 196, 135, 130, 116, 188, 159, 86, 164, 100, 109, 198, 173, 186, 3, 64, 52, 217, 226, 250, 124, 123, 5, 202, 38, 147, 118, 126, 255, 82, 85, 212, 207, 206, 59, 227, 47, 16, 58, 17, 182, 189, 28, 42, 223, 183, 170, 213, 119, 248, 152, 2, 44, 154, 163, 70, 221, 153, 101, 155, 167, 43, 172, 9, 129, 22, 39, 253, 19, 98, 108, 110, 79, 113, 224, 232, 178, 185, 112, 104, 218, 246, 97, 228, 251, 34, 242, 193, 238, 210, 144, 12, 191, 179, 162, 241, 81, 51, 145, 235, 249, 14, 239, 107, 49, 192, 214, 31, 181, 199, 106, 157, 184, 84, 204, 176, 115, 121, 50, 45, 127, 4, 150, 254, 138, 236, 205, 93, 222, 114, 67, 29, 24, 72, 243, 141, 128, 195, 78, 66, 215, 61, 156, 180];

function createNoise(seed: number) {
  const perm = new Array<number>(512), gradP = new Array<Grad>(512);
  let s = Math.floor(seed > 0 && seed < 1 ? seed * 65536 : seed);
  if (s < 256) s |= s << 8;
  for (let i = 0; i < 256; i++) {
    const v = i & 1 ? P[i] ^ (s & 255) : P[i] ^ ((s >> 8) & 255);
    perm[i] = perm[i + 256] = v;
    gradP[i] = gradP[i + 256] = GRAD3[v % 12];
  }
  const fade = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
  const lerp = (a: number, b: number, t: number) => (1 - t) * a + t * b;
  return (x: number, y: number) => {
    let X = Math.floor(x), Y = Math.floor(y);
    x -= X; y -= Y; X &= 255; Y &= 255;
    const n00 = gradP[X + perm[Y]].dot2(x, y), n01 = gradP[X + perm[Y + 1]].dot2(x, y - 1);
    const n10 = gradP[X + 1 + perm[Y]].dot2(x - 1, y), n11 = gradP[X + 1 + perm[Y + 1]].dot2(x - 1, y - 1);
    const u = fade(x);
    return lerp(lerp(n00, n10, u), lerp(n01, n11, u), fade(y));
  };
}

interface Point { x: number; y: number; wx: number; wy: number; cx: number; cy: number; vx: number; vy: number }

export function Waves({ lineColor = 'rgba(0, 71, 171, 0.14)', animate = true, xGap = 12, yGap = 36, waveSpeedX = 0.0125, waveSpeedY = 0.005, waveAmpX = 40, waveAmpY = 20, friction = 0.9, tension = 0.01, maxCursorMove = 120, className = '' }: {
  lineColor?: string; animate?: boolean; xGap?: number; yGap?: number; waveSpeedX?: number; waveSpeedY?: number;
  waveAmpX?: number; waveAmpY?: number; friction?: number; tension?: number; maxCursorMove?: number; className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const container = host.current, el = canvas.current;
    const ctx = el?.getContext('2d');
    if (!container || !el || !ctx) return;
    const noise = createNoise(Math.random());
    const mouse = { x: -10, y: 0, lx: 0, ly: 0, sx: 0, sy: 0, vs: 0, a: 0, set: false };
    let box = { width: 0, height: 0, left: 0, top: 0 };
    let lines: Point[][] = [];
    let frame = 0;

    const setSize = () => {
      const rect = container.getBoundingClientRect();
      box = { width: rect.width, height: rect.height, left: rect.left, top: rect.top };
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      el.width = Math.round(rect.width * dpr);
      el.height = Math.round(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const setLines = () => {
      const total = Math.ceil((box.width + 200) / xGap), points = Math.ceil((box.height + 30) / yGap);
      const xStart = (box.width - xGap * total) / 2, yStart = (box.height - yGap * points) / 2;
      lines = Array.from({ length: total + 1 }, (_, i) => Array.from({ length: points + 1 }, (_, j) =>
        ({ x: xStart + xGap * i, y: yStart + yGap * j, wx: 0, wy: 0, cx: 0, cy: 0, vx: 0, vy: 0 })));
    };
    const move = (time: number) => {
      for (const pts of lines) for (const p of pts) {
        const angle = noise((p.x + time * waveSpeedX) * 0.002, (p.y + time * waveSpeedY) * 0.0015) * 12;
        p.wx = Math.cos(angle) * waveAmpX;
        p.wy = Math.sin(angle) * waveAmpY;
        const dist = Math.hypot(p.x - mouse.sx, p.y - mouse.sy), reach = Math.max(175, mouse.vs);
        if (dist < reach) {
          const force = Math.cos(dist * 0.001) * (1 - dist / reach);
          p.vx += Math.cos(mouse.a) * force * reach * mouse.vs * 0.00065;
          p.vy += Math.sin(mouse.a) * force * reach * mouse.vs * 0.00065;
        }
        p.vx = (p.vx + (0 - p.cx) * tension) * friction;
        p.vy = (p.vy + (0 - p.cy) * tension) * friction;
        p.cx = Math.min(maxCursorMove, Math.max(-maxCursorMove, p.cx + p.vx * 2));
        p.cy = Math.min(maxCursorMove, Math.max(-maxCursorMove, p.cy + p.vy * 2));
      }
    };
    const draw = () => {
      ctx.clearRect(0, 0, box.width, box.height);
      ctx.beginPath();
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 1;
      for (const pts of lines) {
        pts.forEach((p, i) => {
          const last = i === pts.length - 1;
          const x = p.x + p.wx + (last ? 0 : p.cx), y = p.y + p.wy + (last ? 0 : p.cy);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
      }
      ctx.stroke();
    };
    const tick = (time: number) => {
      mouse.sx += (mouse.x - mouse.sx) * 0.1;
      mouse.sy += (mouse.y - mouse.sy) * 0.1;
      const dx = mouse.x - mouse.lx, dy = mouse.y - mouse.ly;
      mouse.vs = Math.min(100, mouse.vs + (Math.hypot(dx, dy) - mouse.vs) * 0.1);
      mouse.lx = mouse.x; mouse.ly = mouse.y;
      mouse.a = Math.atan2(dy, dx);
      move(time);
      draw();
      frame = requestAnimationFrame(tick);
    };
    const onResize = () => { setSize(); setLines(); if (!animate) { move(0); draw(); } };
    const onPointer = (event: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      mouse.x = event.clientX - rect.left;
      mouse.y = event.clientY - rect.top;
      if (!mouse.set) { mouse.sx = mouse.lx = mouse.x; mouse.sy = mouse.ly = mouse.y; mouse.set = true; }
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (animate && document.visibilityState === 'visible') frame = requestAnimationFrame(tick);
    };

    setSize(); setLines();
    window.addEventListener('resize', onResize);
    if (animate) {
      frame = requestAnimationFrame(tick);
      window.addEventListener('pointermove', onPointer);
      document.addEventListener('visibilitychange', onVisibility);
    } else { move(0); draw(); }
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('pointermove', onPointer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [animate, lineColor, xGap, yGap, waveSpeedX, waveSpeedY, waveAmpX, waveAmpY, friction, tension, maxCursorMove]);

  return <div ref={host} className={`hrms-waves ${className}`} aria-hidden="true"><canvas ref={canvas} /></div>;
}
