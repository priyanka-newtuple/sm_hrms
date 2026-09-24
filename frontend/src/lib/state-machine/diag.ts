/**
 * TEMPORARY DIAGNOSTIC LOGGING — remove once the method_refs save bug is closed.
 *
 * Every line is prefixed `[DIAG]` so the whole thing greps and strips cleanly:
 *   grep -rn "\[DIAG\]" frontend/src
 *
 * Dev-build only (`import.meta.env.DEV`), and it only ever reads: nothing here
 * patches a global. An earlier version wrapped `window.setTimeout` and
 * `requestAnimationFrame` for the whole app; that is gone.
 *
 * Design rules learned the hard way:
 *  - Never log a *reconstructed* value. Log the exact object handed to the
 *    setter, or the log will disagree with reality (it did, once).
 *  - Every line carries a sequence id and a caller tag pulled from the real
 *    stack, so two lines a tenth of a millisecond apart are provably the same
 *    event rather than merely adjacent.
 */

import type { StateMachineDocument } from './types';

/** Dev-build only: these lines must never reach a production console. */
const DIAG_ENABLED = import.meta.env.DEV;

let SEQ = 0;

/** Monotonic id so causally-related lines can be tied together unambiguously. */
function nextSeq(): string {
  SEQ += 1;
  return `#${String(SEQ).padStart(4, '0')}`;
}

/**
 * Top frames of the live stack, so each line names the function that produced
 * it instead of relying on a hand-written label matching reality.
 */
function callerTag(skip = 3): string {
  const raw = new Error().stack ?? '';
  const frames = raw
    .split('\n')
    .slice(skip)
    .map((f) => f.trim().replace(/^at\s+/, ''))
    .filter((f) => f && !f.includes('/lib/state-machine/diag'))
    .slice(0, 3)
    .map((f) => {
      const named = /^(?:async\s+)?([\w$.<>]+)\s*\(/.exec(f);
      const loc = /([\w.-]+\.tsx?):(\d+):\d+/.exec(f);
      const fn = named?.[1] ?? '<anon>';
      return loc ? `${fn}@${loc[1]}:${loc[2]}` : fn;
    });
  return frames.join(' < ') || '<no-stack>';
}

/** Compact per-state method_refs snapshot, e.g. `INITIAL=[m-abc123]; DONE=[]`. */
export function methodRefsSnapshot(doc: StateMachineDocument | null | undefined): string {
  const states = doc?.definition?.states;
  if (!Array.isArray(states)) return '<no states>';
  if (states.length === 0) return '<empty states[]>';
  return states
    .map((state) => {
      const refs = state.method_refs ?? [];
      return `${state.name}=[${refs.map((ref) => ref.method_id.slice(0, 8)).join(',')}]`;
    })
    .join('; ');
}

function stamp(): string {
  return performance.now().toFixed(1).padStart(9, ' ');
}

/** One timeline line: `[DIAG] #0001 t=123.4ms <event> | <detail> @ <caller>`. */
export function diagLog(event: string, detail?: string): void {
  if (!DIAG_ENABLED) return;
  const head = `[DIAG] ${nextSeq()} t=${stamp()}ms ${event}`;
  const body = detail === undefined ? head : `${head} | ${detail}`;
  // eslint-disable-next-line no-console
  console.log(`${body}  @ ${callerTag()}`);
}

/**
 * Log a document commit. `committed` MUST be the same object reference that is
 * then handed to the setter — pass the variable, never an inline rebuild.
 */
export function diagLogCommit(
  trigger: string,
  before: StateMachineDocument | null | undefined,
  committed: StateMachineDocument,
  extra?: string,
): void {
  if (!DIAG_ENABLED) return;
  const from = methodRefsSnapshot(before);
  const to = methodRefsSnapshot(committed);
  const verdict = from === to ? 'method_refs UNCHANGED' : 'method_refs CHANGED';
  const suffix = extra ? ` :: ${extra}` : '';
  const head = `[DIAG] ${nextSeq()} t=${stamp()}ms COMMIT<${trigger}> ${verdict} :: before{${from}} -> COMMITTED{${to}}${suffix}`;
  // eslint-disable-next-line no-console
  console.log(`${head}  @ ${callerTag()}`);
}

/** Log a direct write to a doc-holding ref, separate from any onChange call. */
export function diagLogRefWrite(
  refName: string,
  previous: StateMachineDocument | null | undefined,
  next: StateMachineDocument | null | undefined,
): void {
  if (!DIAG_ENABLED) return;
  const from = methodRefsSnapshot(previous);
  const to = methodRefsSnapshot(next);
  const verdict = from === to ? 'UNCHANGED' : 'CHANGED';
  const head = `[DIAG] ${nextSeq()} t=${stamp()}ms REF-WRITE<${refName}> ${verdict} :: was{${from}} -> now{${to}}`;
  // eslint-disable-next-line no-console
  console.log(`${head}  @ ${callerTag()}`);
}
