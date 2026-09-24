/**
 * RichTextEditor — GitHub-style markdown editor with Write / Preview tabs.
 *
 * Write tab  : plain textarea, raw markdown visible (no auto-conversion).
 * Preview tab: normalizeToHtml converts markdown/HTML → RichTextDisplay.
 * Save        : stores raw markdown string; FieldBox converts at read time.
 *
 * Toolbar inserts markdown syntax (not TipTap commands) so what you type
 * in Write mode is exactly what gets saved.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  Bold,
  Italic,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Code,
  FileCode,
  Quote,
  Link as LinkIcon,
  Minus,
  Eye,
  Pencil,
} from 'lucide-react';

import { cn } from '@/lib/utils';
import { normalizeToHtml } from '@/core/utils/markdownToHtml';

interface RichTextEditorProps {
  value: string;
  onChange: (markdown: string) => void;
  placeholder?: string;
  disabled?: boolean;
  invalid?: boolean;
  /** Field-level appearance override (FormField.style_config). */
  backgroundColor?: string;
  textColor?: string;
}

// ─── Sanitization (used by RichTextDisplay) ───────────────────────────────────

const ALLOWED_TAGS = new Set([
  'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'strike',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'pre', 'code',
  'a', 'mark', 'span', 'hr',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th',
]);
const ALLOWED_ATTRS = new Set([
  'href', 'target', 'rel', 'style', 'class', 'data-color',
  'colspan', 'rowspan', 'scope',
]);
const SAFE_LINK_PROTOCOLS = new Set(['http:', 'https:', 'mailto:', 'tel:']);

function sanitizeHref(rawHref: string): string | null {
  const href = rawHref.trim();
  if (!href) return null;
  if (href.startsWith('#')) return href;

  try {
    const base =
      typeof window !== 'undefined' && window.location?.href
        ? window.location.href
        : 'https://sanitizer.invalid/';
    const parsed = new URL(href, base);
    return SAFE_LINK_PROTOCOLS.has(parsed.protocol) ? href : null;
  } catch {
    return null;
  }
}

function sanitizeHTML(html: string): string {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  function walk(node: Node): void {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as Element;
        if (!ALLOWED_TAGS.has(el.tagName.toLowerCase())) {
          el.replaceWith(document.createTextNode(el.textContent ?? ''));
          continue;
        }
        for (const attr of Array.from(el.attributes)) {
          if (!ALLOWED_ATTRS.has(attr.name)) el.removeAttribute(attr.name);
        }
        if (el.tagName === 'A') {
          const href = el.getAttribute('href') ?? '';
          const safeHref = sanitizeHref(href);
          if (safeHref) {
            el.setAttribute('href', safeHref);
          } else {
            el.removeAttribute('href');
          }
        }
        walk(el);
      }
    }
  }
  walk(doc.body);
  return doc.body.innerHTML;
}

function stripLeadingEmptyBlocks(html: string): string {
  return html.replace(
    /^(?:\s|<p>(?:\s|&nbsp;|<br\s*\/?>)*<\/p>|<br\s*\/?>)+(?=<(table|ul|ol|pre|blockquote|h[1-6]|hr)\b)/i,
    '',
  );
}

// ─── Toolbar helpers ──────────────────────────────────────────────────────────

/** Wrap current selection with `before` and `after` markdown markers. */
function wrapSel(
  ta: HTMLTextAreaElement,
  value: string,
  before: string,
  after: string,
  onChange: (v: string) => void,
) {
  const s = ta.selectionStart;
  const e = ta.selectionEnd;
  const sel = value.slice(s, e) || 'text';
  const next = value.slice(0, s) + before + sel + after + value.slice(e);
  onChange(next);
  requestAnimationFrame(() => {
    ta.focus();
    ta.setSelectionRange(s + before.length, s + before.length + sel.length);
  });
}

/** Prepend `prefix` to the start of the line the cursor is on. */
function prefixLine(
  ta: HTMLTextAreaElement,
  value: string,
  prefix: string,
  onChange: (v: string) => void,
) {
  const s = ta.selectionStart;
  const lineStart = value.lastIndexOf('\n', s - 1) + 1;
  const next = value.slice(0, lineStart) + prefix + value.slice(lineStart);
  onChange(next);
  requestAnimationFrame(() => {
    ta.focus();
    ta.setSelectionRange(s + prefix.length, s + prefix.length);
  });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ToolBtn({
  onClick,
  title,
  children,
}: {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      {children}
    </button>
  );
}

function Sep() {
  return <div className="mx-0.5 h-5 w-px bg-border" />;
}

// ─── Main component ───────────────────────────────────────────────────────────

const I = 15;

export default function RichTextEditor({
  value,
  onChange,
  placeholder,
  disabled = false,
  invalid = false,
  backgroundColor,
  textColor,
}: RichTextEditorProps) {
  const hasContent = value.trim().length > 0;
  const [preview, setPreview] = useState(hasContent);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const internalUpdateRef = useRef(false);

  useEffect(() => {
    if (internalUpdateRef.current) {
      internalUpdateRef.current = false;
      if (!hasContent) setPreview(false);
      return;
    }

    setPreview(hasContent);
  }, [hasContent, value]);

  const emitChange = useCallback((next: string) => {
    internalUpdateRef.current = true;
    onChange(next);
  }, [onChange]);

  const wrap = useCallback(
    (before: string, after: string) => {
      if (taRef.current) wrapSel(taRef.current, value, before, after, emitChange);
    },
    [value, emitChange],
  );

  const pre = useCallback(
    (pfx: string) => {
      if (taRef.current) prefixLine(taRef.current, value, pfx, emitChange);
    },
    [value, emitChange],
  );

  const insertLink = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const e = ta.selectionEnd;
    const sel = value.slice(s, e);
    const url = window.prompt('URL', 'https://');
    if (!url) return;
    const text = sel || 'link text';
    emitChange(value.slice(0, s) + `[${text}](${url})` + value.slice(e));
  }, [value, emitChange]);

  const insertHr = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    const s = ta.selectionStart;
    const insert = '\n\n---\n\n';
    emitChange(value.slice(0, s) + insert + value.slice(s));
    requestAnimationFrame(() => {
      ta.focus();
      ta.setSelectionRange(s + insert.length, s + insert.length);
    });
  }, [value, emitChange]);

  // Auto-grow textarea to content height, capped at 400 px.
  const autoResize = useCallback((ta: HTMLTextAreaElement) => {
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 400)}px`;
  }, []);

  const previewHtml = useMemo(
    () => (preview ? normalizeToHtml(value || '') : ''),
    [preview, value],
  );
  const previewStartsWithTable = useMemo(
    () => /^\s*(?:<p>(?:\s|&nbsp;|<br\s*\/?>)*<\/p>\s*)*<table\b/i.test(previewHtml),
    [previewHtml],
  );

  return (
    <div
      style={backgroundColor ? { backgroundColor } : undefined}
      className={cn(
        'rounded-xl border transition-colors',
        !backgroundColor && 'bg-background',
        invalid
          ? 'border-destructive'
          : 'border-gray-300 focus-within:border-cobalt focus-within:ring-2 focus-within:ring-cobalt/20',
        disabled && 'opacity-60 pointer-events-none',
      )}
    >
      {!disabled && (
        <div className="flex flex-wrap items-center gap-0.5 border-b border-gray-200 px-2 py-1">
          {/* Write / Preview tabs */}
          <button
            type="button"
            onClick={() => setPreview(false)}
            className={cn(
              'flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors',
              !preview
                ? 'bg-cobalt/10 text-cobalt'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            <Pencil size={11} />
            Write
          </button>
          <button
            type="button"
            onClick={() => setPreview(true)}
            className={cn(
              'flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors',
              preview
                ? 'bg-cobalt/10 text-cobalt'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            <Eye size={11} />
            Preview
          </button>

          {/* Formatting toolbar — only in Write mode */}
          {!preview && (
            <>
              <Sep />
              <ToolBtn onClick={() => wrap('**', '**')} title="Bold (Ctrl+B)"><Bold size={I} /></ToolBtn>
              <ToolBtn onClick={() => wrap('*', '*')} title="Italic (Ctrl+I)"><Italic size={I} /></ToolBtn>
              <ToolBtn onClick={() => wrap('~~', '~~')} title="Strikethrough"><Strikethrough size={I} /></ToolBtn>
              <ToolBtn onClick={() => wrap('`', '`')} title="Inline code"><Code size={I} /></ToolBtn>

              <Sep />
              <ToolBtn onClick={() => pre('# ')} title="Heading 1"><Heading1 size={I} /></ToolBtn>
              <ToolBtn onClick={() => pre('## ')} title="Heading 2"><Heading2 size={I} /></ToolBtn>
              <ToolBtn onClick={() => pre('### ')} title="Heading 3"><Heading3 size={I} /></ToolBtn>

              <Sep />
              <ToolBtn onClick={() => pre('- ')} title="Bullet list"><List size={I} /></ToolBtn>
              <ToolBtn onClick={() => pre('1. ')} title="Numbered list"><ListOrdered size={I} /></ToolBtn>

              <Sep />
              <ToolBtn onClick={() => wrap('\n```\n', '\n```\n')} title="Code block"><FileCode size={I} /></ToolBtn>
              <ToolBtn onClick={() => pre('> ')} title="Blockquote"><Quote size={I} /></ToolBtn>
              <ToolBtn onClick={insertLink} title="Link"><LinkIcon size={I} /></ToolBtn>
              <ToolBtn onClick={insertHr} title="Horizontal rule"><Minus size={I} /></ToolBtn>
            </>
          )}
        </div>
      )}

      {preview ? (
        <div
          // The rendered markdown sets `text-foreground` on its own root and
          // headings, and a class beats an inherited colour — so the token
          // itself is overridden for this subtree rather than just `color`.
          // Deliberately muted parts (blockquote, code blocks) keep their own.
          style={
            textColor
              ? ({ color: textColor, '--foreground': textColor } as CSSProperties)
              : undefined
          }
          className={cn(
            'min-h-[220px] max-h-[480px] overflow-y-auto px-3 pb-2.5',
            previewStartsWithTable ? 'pt-0' : 'pt-2.5',
          )}
        >
          {previewHtml
            ? <RichTextDisplay html={previewHtml} />
            : <span className="text-sm text-muted-foreground">Nothing to preview</span>
          }
        </div>
      ) : (
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => {
            emitChange(e.target.value);
            autoResize(e.target);
          }}
          onFocus={(e) => autoResize(e.target)}
          placeholder={placeholder ?? 'Write description here…'}
          disabled={disabled}
          style={textColor ? { color: textColor } : undefined}
          className={cn(
            'w-full resize-none bg-transparent px-3 py-2.5 text-sm leading-relaxed outline-none',
            'min-h-[220px] overflow-y-auto',
            'placeholder:text-muted-foreground/50',
            'font-mono',           // monospace so markdown syntax reads clearly
          )}
        />
      )}
    </div>
  );
}

// ─── Read-only renderer ───────────────────────────────────────────────────────

/**
 * Read-only renderer for rich text HTML content.
 */
export function RichTextDisplay({ html }: { html: string }) {
  const sanitized = useMemo(() => stripLeadingEmptyBlocks(sanitizeHTML(html)), [html]);

  if (!html || html === '<p></p>') return <span className="text-muted-foreground">—</span>;

  return (
    <div
      className={cn(
        'leading-relaxed text-foreground',
        // Headings — clear visual hierarchy
        '[&_h1]:text-2xl [&_h1]:font-bold [&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-foreground [&_h1]:leading-tight',
        '[&_h2]:text-xl [&_h2]:font-semibold [&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-foreground [&_h2]:leading-tight',
        '[&_h3]:text-lg [&_h3]:font-semibold [&_h3]:mt-3 [&_h3]:mb-1.5 [&_h3]:text-foreground',
        // First child: no top margin
        '[&>*:first-child]:mt-0',
        // Lists
        '[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2',
        '[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2',
        '[&_li]:my-1 [&_li]:text-sm',
        // Paragraphs
        '[&_p]:text-sm [&_p]:mb-2 [&_p:last-child]:mb-0',
        // Blockquote
        '[&_blockquote]:border-l-[3px] [&_blockquote]:border-cobalt/50 [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_blockquote]:my-3 [&_blockquote]:py-0.5 [&_blockquote]:italic',
        // Inline code
        '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs [&_code]:text-foreground',
        // Code block — reset inline code styles inside pre
        '[&_pre]:rounded-lg [&_pre]:bg-gray-900 [&_pre]:p-4 [&_pre]:overflow-x-auto [&_pre]:my-3',
        '[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-gray-100 [&_pre_code]:text-xs [&_pre_code]:rounded-none',
        // Tables
        '[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:overflow-hidden [&_table]:rounded-lg [&_table]:border [&_table]:border-border',
        '[&_table:first-child]:mt-0',
        '[&_thead]:bg-muted/70',
        '[&_th]:border [&_th]:border-border [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide',
        '[&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_td]:align-top [&_td]:text-sm',
        '[&_tbody_tr:nth-child(even)]:bg-muted/20',
        // Misc
        '[&_a]:text-cobalt [&_a]:underline [&_a]:underline-offset-2 [&_a]:hover:opacity-80',
        '[&_mark]:rounded [&_mark]:px-0.5',
        '[&_hr]:my-4 [&_hr]:border-gray-200',
        '[&_s]:line-through [&_s]:opacity-60',
        '[&_strong]:font-semibold',
      )}
      dangerouslySetInnerHTML={{ __html: sanitized }}
    />
  );
}
