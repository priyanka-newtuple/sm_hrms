import type { ReactNode } from 'react';

// Matches http(s):// URLs and bare www. URLs. Kept intentionally simple and
// anchored to safe schemes only — nothing else is ever turned into an href, so
// `javascript:` / `data:` strings can never become links.
const URL_RE = /((?:https?:\/\/|www\.)[^\s<]+)/gi;

// Punctuation that commonly abuts a URL in prose but isn't part of it, e.g.
// "see https://x.com." — the period should stay outside the link. Note: `)` is
// handled separately (see splitTrailingPunctuation) so that balanced parens
// inside a URL, like Wikipedia's `/wiki/C_(programming_language)`, are kept.
const TRAILING_PUNCT = new Set(['.', ',', ';', ':', '!', '?', ']', '}', "'", '"']);

/**
 * Splits a matched URL into its real value and any trailing punctuation that
 * leaked in from surrounding prose. A trailing `)` is only peeled off when it is
 * unbalanced within the URL — a balanced `(...)` pair stays part of the link.
 */
function splitTrailingPunctuation(url: string): [core: string, trailing: string] {
  let end = url.length;
  while (end > 0) {
    const ch = url[end - 1];
    if (ch === ')') {
      const core = url.slice(0, end);
      const opens = (core.match(/\(/g) ?? []).length;
      const closes = (core.match(/\)/g) ?? []).length;
      if (closes <= opens) break; // balanced — this ) belongs to the URL
      end -= 1; // unbalanced trailing ) — strip it
    } else if (TRAILING_PUNCT.has(ch)) {
      end -= 1;
    } else {
      break;
    }
  }
  return [url.slice(0, end), url.slice(end)];
}

/**
 * Splits free text into React nodes, turning bare URLs into safe external links
 * styled like the app's other links. Non-URL text is returned as plain strings.
 *
 * Only `http`/`https` (and `www.`, which is prefixed with `https://`) become
 * links; every other substring is emitted verbatim, so untrusted schemes are
 * never rendered as clickable hrefs.
 *
 * @param text - the raw text to scan.
 * @param keyPrefix - namespace for React keys when several calls render as
 *   siblings (callers often map over segments).
 */
export function linkify(text: string, keyPrefix = 'lnk'): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  URL_RE.lastIndex = 0;

  while ((match = URL_RE.exec(text)) !== null) {
    const raw = match[0];
    // Peel trailing punctuation back out of the link and into plain text.
    const [url, trailing] = splitTrailingPunctuation(raw);
    if (!url) continue; // punctuation-only match — skip

    if (match.index > last) nodes.push(text.slice(last, match.index));

    const href = url.startsWith('www.') ? `https://${url}` : url;
    nodes.push(
      <a
        key={`${keyPrefix}-${match.index}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-cobalt hover:text-cobalt-dark underline hover:no-underline break-words [overflow-wrap:anywhere]"
      >
        {url}
      </a>,
    );

    if (trailing) nodes.push(trailing);
    last = match.index + raw.length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
