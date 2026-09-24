/**
 * Markdown ↔ HTML utilities for rendering agent/LLM output in textarea fields.
 *
 * Why this exists: TipTap is a WYSIWYG editor (stores HTML). Agents write
 * markdown. This module converts at the read boundary so rich text fields
 * render correctly regardless of whether the stored value is markdown or HTML.
 */

const HTML_TAG_RE = /^<(p|div|br|h[1-6]|ul|ol|li|blockquote|pre|hr|strong|b|em|i|u|s|del|strike|a|mark|span|code|table|thead|tbody|tfoot|tr|td|th)\b/i;
const HTML_BLOCK_LINE_RE = /^<(table|thead|tbody|tfoot|tr|td|th|div|blockquote|pre|ul|ol|li|h[1-6]|p|hr)\b/i;
const HTML_MARKDOWN_WRAPPER_TAG_RE = /^(p|div|br)$/i;

/** True when the string is raw markdown (not HTML, not plain text). */
export function looksLikeMarkdown(text: string): boolean {
  if (!text || text.trim() === '') return false;
  if (HTML_TAG_RE.test(text.trim())) return false;
  return (
    /^#{1,6}\s/m.test(text) ||
    /\*\*[^*\n]+\*\*/m.test(text) ||
    /(^|[^\w*])\*[^*\n]+\*(?!\*)/m.test(text) ||
    /`[^`\n]+`/m.test(text) ||
    /\[[^\]]+\]\(([^)]+)\)/m.test(text) ||
    /^[-*+]\s/m.test(text) ||
    /^\d+\.\s/m.test(text) ||
    /^```/m.test(text) ||
    /^>\s/m.test(text) ||
    /~~[^~\n]+~~/m.test(text)
  );
}

/**
 * Extract plain text from HTML, preserving logical line breaks.
 * Block elements (p, li, h*, div) each become a new line.
 */
function htmlToText(html: string): string {
  return html
    .replace(/<\/(p|div|li|h[1-6]|blockquote|pre|tr)>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .trim();
}

/**
 * True when TipTap stored pasted markdown inside bare <p> tags.
 * E.g. <p>## Heading</p> or <p>- list item</p>.
 * This happens because TipTap's paste rules handle **bold** and - lists
 * but not # headings.
 */
export function htmlContainsRawMarkdown(html: string): boolean {
  const trimmed = html.trim();
  if (!HTML_TAG_RE.test(trimmed)) return false;
  // If any non-wrapper tag (not p/div/br) is present, the HTML is already structured.
  if (/<\/?(?!(?:p|div|br)\b)[a-z][^>]*/i.test(trimmed)) return false;
  return looksLikeMarkdown(htmlToText(html));
}

/**
 * Convert HTML that wraps raw markdown (from TipTap paste) to proper HTML.
 */
export function convertHtmlMarkdown(html: string): string {
  return markdownToHtml(htmlToText(html));
}

function isMarkdownWrapperNode(node: Node): node is Element {
  if (node.nodeType !== Node.ELEMENT_NODE) return false;
  const el = node as Element;
  if (!HTML_MARKDOWN_WRAPPER_TAG_RE.test(el.tagName)) return false;
  if (el.tagName === 'BR') return true;
  return Array.from(el.childNodes).every(
    (child) =>
      child.nodeType === Node.TEXT_NODE ||
      (child.nodeType === Node.ELEMENT_NODE && (child as Element).tagName === 'BR'),
  );
}

function serializeHtmlNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.textContent ?? '');
  if (node.nodeType === Node.ELEMENT_NODE) return (node as Element).outerHTML;
  return '';
}

function extractMarkdownWrapperText(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? '';
  if (node.nodeType === Node.ELEMENT_NODE) return htmlToText((node as Element).outerHTML);
  return '';
}

function normalizeMixedHtmlMarkdown(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const nodes = Array.from(doc.body.childNodes);
  const out: string[] = [];
  let i = 0;

  while (i < nodes.length) {
    if (!isMarkdownWrapperNode(nodes[i])) {
      out.push(serializeHtmlNode(nodes[i]));
      i++;
      continue;
    }

    const run: Node[] = [];
    let j = i;
    while (j < nodes.length && isMarkdownWrapperNode(nodes[j])) {
      run.push(nodes[j]);
      j++;
    }

    const markdown = run.map(extractMarkdownWrapperText).join('\n').trim();
    if (markdown && looksLikeMarkdown(markdown)) {
      out.push(markdownToHtml(markdown));
    } else {
      out.push(...run.map(serializeHtmlNode));
    }

    i = j;
  }

  return out.join('');
}

function collectRawHtmlBlock(lines: string[], start: number): { html: string; next: number } | null {
  const first = lines[start].trim();
  if (/^<table\b/i.test(first)) {
    const block: string[] = [];
    let i = start;
    while (i < lines.length) {
      block.push(lines[i]);
      if (/<\/table>\s*$/i.test(lines[i].trim())) {
        return { html: block.join('\n'), next: i + 1 };
      }
      i++;
    }
    return { html: block.join('\n'), next: i };
  }

  if (HTML_BLOCK_LINE_RE.test(first)) {
    return { html: lines[start], next: start + 1 };
  }

  return null;
}

function plainTextToHtml(text: string): string {
  const paragraphs = text
    .trim()
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  if (paragraphs.length === 0) return '';

  return paragraphs
    .map((paragraph) => `<p>${escapeHtml(paragraph).replace(/\n/g, '<br>')}</p>`)
    .join('');
}

// ─── Inline formatter ────────────────────────────────────────────────────────

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inlineFormat(text: string): string {
  return (
    text
      // Bold + Italic  ***text***
      .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
      // Bold  **text**  __text__
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/__(.+?)__/g, '<strong>$1</strong>')
      // Italic  *text*  (word-boundary _ to avoid mid-word false positives)
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/(?<![_a-zA-Z0-9])_([^_\n]+?)_(?![_a-zA-Z0-9])/g, '<em>$1</em>')
      // Strikethrough  ~~text~~
      .replace(/~~(.+?)~~/g, '<s>$1</s>')
      // Inline code  `code`
      .replace(/`([^`\n]+)`/g, (_, code) => `<code>${escapeHtml(code)}</code>`)
      // Links  [text](url)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
  );
}

type ParsedBlock = { html: string; next: number } | null;

function parseFencedCodeBlock(lines: string[], start: number): ParsedBlock {
  const line = lines[start];
  if (!line.startsWith('```')) return null;

  const lang = line.slice(3).trim();
  const code: string[] = [];
  let i = start + 1;

  while (i < lines.length && !/^```\s*$/.test(lines[i])) {
    code.push(lines[i]);
    i++;
  }

  const cls = lang ? ` class="language-${escapeHtml(lang)}"` : '';
  return {
    html: `<pre><code${cls}>${escapeHtml(code.join('\n'))}</code></pre>`,
    next: i + 1,
  };
}

function parseHeading(line: string): string | null {
  const match = line.match(/^(#{1,6})\s+(.+)$/);
  if (!match) return null;

  const level = Math.min(match[1].length, 3);
  return `<h${level}>${inlineFormat(match[2].trim())}</h${level}>`;
}

function parseHorizontalRule(line: string): string | null {
  return /^[-*_]{3,}\s*$/.test(line) ? '<hr>' : null;
}

function parseBlockquote(lines: string[], start: number): ParsedBlock {
  if (!/^>\s?/.test(lines[start])) return null;

  const quotedLines: string[] = [];
  let i = start;

  while (i < lines.length && /^>\s?/.test(lines[i])) {
    quotedLines.push(lines[i].replace(/^>\s?/, ''));
    i++;
  }

  return {
    html: `<blockquote><p>${inlineFormat(quotedLines.join(' '))}</p></blockquote>`,
    next: i,
  };
}

function parseUnorderedList(lines: string[], start: number): ParsedBlock {
  if (!/^[-*+]\s/.test(lines[start])) return null;

  const items: string[] = [];
  let i = start;

  while (i < lines.length && /^[-*+]\s/.test(lines[i])) {
    items.push(`<li>${inlineFormat(lines[i].replace(/^[-*+]\s+/, ''))}</li>`);
    i++;
  }

  return { html: `<ul>${items.join('')}</ul>`, next: i };
}

function parseOrderedList(lines: string[], start: number): ParsedBlock {
  if (!/^\d+\.\s/.test(lines[start])) return null;

  const items: string[] = [];
  let i = start;

  while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
    items.push(`<li>${inlineFormat(lines[i].replace(/^\d+\.\s+/, ''))}</li>`);
    i++;
  }

  return { html: `<ol>${items.join('')}</ol>`, next: i };
}

function isParagraphLine(line: string): boolean {
  return (
    line.trim() !== '' &&
    !/^#{1,6}\s/.test(line) &&
    !line.startsWith('```') &&
    !HTML_BLOCK_LINE_RE.test(line.trim()) &&
    !/^>\s?/.test(line) &&
    !/^[-*+]\s/.test(line) &&
    !/^\d+\.\s/.test(line) &&
    !/^[-*_]{3,}\s*$/.test(line)
  );
}

function parseParagraph(lines: string[], start: number): ParsedBlock {
  if (!isParagraphLine(lines[start])) return null;

  const paragraph: string[] = [];
  let i = start;

  while (i < lines.length && isParagraphLine(lines[i])) {
    paragraph.push(lines[i]);
    i++;
  }

  return { html: `<p>${inlineFormat(paragraph.join('<br>'))}</p>`, next: i };
}

// ─── Block converter ─────────────────────────────────────────────────────────

/**
 * Convert a markdown string to TipTap-compatible HTML.
 * Safe to pass to `editor.commands.insertContent()` or `RichTextDisplay`.
 *
 * Handles: headings, fenced code blocks, blockquotes, ordered/unordered
 * lists, horizontal rules, paragraphs, and all inline formats.
 */
export function markdownToHtml(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const parsedBlock =
      parseFencedCodeBlock(lines, i) ??
      collectRawHtmlBlock(lines, i) ??
      parseBlockquote(lines, i) ??
      parseUnorderedList(lines, i) ??
      parseOrderedList(lines, i) ??
      parseParagraph(lines, i);

    if (parsedBlock) {
      out.push(parsedBlock.html);
      i = parsedBlock.next;
      continue;
    }

    const heading = parseHeading(line);
    if (heading) {
      out.push(heading);
      i++;
      continue;
    }

    const horizontalRule = parseHorizontalRule(line);
    if (horizontalRule) {
      out.push(horizontalRule);
      i++;
      continue;
    }

    i++;
  }

  return out.join('') || '<p></p>';
}

/**
 * Normalize any textarea field value to display HTML.
 * Handles raw markdown, HTML-wrapped markdown, and clean TipTap HTML.
 */
export function normalizeToHtml(value: string): string {
  if (!value.trim()) return '';
  if (HTML_TAG_RE.test(value.trim())) {
    return normalizeMixedHtmlMarkdown(value);
  }
  if (looksLikeMarkdown(value)) return markdownToHtml(value);
  return plainTextToHtml(value);
}
