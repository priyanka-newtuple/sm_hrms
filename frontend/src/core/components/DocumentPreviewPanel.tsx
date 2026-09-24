/**
 * DocumentPreviewPanel
 *
 * Preview surface beside the entity detail sheet / full-page view. Shows the
 * active document from useDocumentPreviewStore with arrow navigation and a
 * download button. Renders nothing when there are no documents; hidden below
 * the lg breakpoint (callers keep list-row download for narrow screens).
 *
 * Layout-agnostic: it fills its container and lets the caller own width and
 * borders via `className`. Collapsed, it shrinks to a slim clickable rail.
 */

import { useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  Maximize2,
  PanelRightClose,
  PanelRightOpen,
  Loader2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDocumentDownload } from '../hooks/useDocumentDownload';
import { getFileExtension, getFileIcon, useDocumentPreview } from '../hooks/useDocumentPreview';
import { useDocumentPreviewStore } from '../stores/documentPreviewStore';

type PreviewPanelLayout = 'sheet' | 'page';

/** Expanded-panel sizing per layout. `sheet` = fixed-width column beside the
 *  detail sheet; `page` = slimmer docked sidebar on the full-page view, at full
 *  height, so the detail column keeps the room. Collapsed-rail sizing is
 *  layout-independent. Add a key here to extend — no internals to touch. */
const LAYOUT_CLASSES: Record<PreviewPanelLayout, string> = {
  sheet: 'w-[34rem] shrink-0',
  page: 'h-full w-[clamp(26rem,34vw,31rem)] shrink-0',
};

type DocumentPreviewPanelProps = {
  className?: string;
  layout?: PreviewPanelLayout;
};

export default function DocumentPreviewPanel({
  className,
  layout = 'sheet',
}: DocumentPreviewPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const docs = useDocumentPreviewStore((s) => s.docs);
  const activeIndex = useDocumentPreviewStore((s) => s.activeIndex);
  const collapsed = useDocumentPreviewStore((s) => s.collapsed);
  const setCollapsed = useDocumentPreviewStore((s) => s.setCollapsed);
  const next = useDocumentPreviewStore((s) => s.next);
  const prev = useDocumentPreviewStore((s) => s.prev);

  const activeDoc = docs[activeIndex] ?? null;
  const isImagePreview = activeDoc
    ? ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(
        getFileExtension(activeDoc.filename),
      )
    : false;
  // Skip fetching while collapsed — the rail shows no content.
  const {
    loading,
    error,
    blobUrl,
    csvRows,
    excelBlob,
    excelRendering,
    excelContainerRef,
    wordBlob,
    wordRendering,
    wordContainerRef,
    unsupported,
  } = useDocumentPreview(collapsed ? null : activeDoc);
  const { download, error: downloadError } = useDocumentDownload(activeDoc);

  if (!activeDoc) return null;

  // Slim rail — click anywhere to re-expand.
  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className={cn(
          'hidden h-full w-12 shrink-0 flex-col items-center gap-4 bg-card py-4 transition-colors hover:bg-primary/5 lg:flex',
          className,
        )}
        title={`Show preview — ${activeDoc.filename}`}
      >
        <PanelRightOpen className="h-4 w-4 shrink-0 text-primary" />
        <span className="text-xs font-medium tracking-wide text-muted-foreground [writing-mode:vertical-rl]">
          Preview
        </span>
      </button>
    );
  }

  const documentNavigation = docs.length > 1 && (
    <div className="flex items-center rounded-lg bg-muted/70 p-0.5">
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={prev}
        disabled={activeIndex === 0}
        title="Previous document"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="min-w-[2.75rem] text-center text-xs tabular-nums text-muted-foreground">
        {activeIndex + 1} / {docs.length}
      </span>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={next}
        disabled={activeIndex >= docs.length - 1}
        title="Next document"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );

  const previewBody = (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-muted/40">
      {loading ? (
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      ) : error ? (
        <div className="flex flex-col items-center gap-3 px-6 text-center">
          <AlertCircle className="h-6 w-6 text-destructive" />
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={() => void download()}>
            <Download className="mr-2 h-4 w-4" />
            {activeDoc.source_url ? 'Open or download source' : 'Download'}
          </Button>
          {downloadError && <p className="text-xs text-destructive">{downloadError}</p>}
        </div>
      ) : csvRows ? (
        <div className="h-full w-full overflow-auto bg-card text-foreground">
          <table className="border-collapse text-sm">
            <tbody>
              {csvRows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className={`whitespace-nowrap border border-border px-2 py-1 ${
                        ri === 0 ? 'bg-muted font-semibold' : ''
                      }`}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : excelBlob ? (
        <div className="relative h-full w-full bg-card">
          <div ref={excelContainerRef} className="h-full w-full" />
          {excelRendering && (
            <div className="absolute inset-0 flex items-center justify-center bg-card/70">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          )}
        </div>
      ) : wordBlob ? (
        <div className="relative h-full w-full overflow-auto bg-card">
          <div ref={wordContainerRef} className="h-full w-full" />
          {wordRendering && (
            <div className="absolute inset-0 flex items-center justify-center bg-card/70">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          )}
        </div>
      ) : blobUrl && isImagePreview ? (
        <img
          src={blobUrl}
          alt={`Preview ${activeDoc.filename}`}
          referrerPolicy={activeDoc.source_url ? 'no-referrer' : undefined}
          className="h-full w-full object-contain p-4"
        />
      ) : blobUrl ? (
        <iframe
          src={blobUrl}
          className="h-full w-full border-0"
          title={`Preview ${activeDoc.filename}`}
          referrerPolicy={activeDoc.source_url ? 'no-referrer' : undefined}
          sandbox={activeDoc.source_url ? 'allow-scripts allow-same-origin' : undefined}
        />
      ) : unsupported ? (
        <div className="flex flex-col items-center gap-3 px-6 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
            {getFileIcon(activeDoc.filename)}
          </span>
          <p className="text-sm font-medium text-foreground">No inline preview available</p>
          <p className="max-w-xs text-xs text-muted-foreground">
            This file type can’t be previewed in the browser. Download it to view.
          </p>
          <Button variant="outline" size="sm" onClick={download}>
            <Download className="mr-2 h-4 w-4" />
            {activeDoc.source_url ? 'Open or download source' : 'Download'}
          </Button>
          {downloadError && <p className="text-xs text-destructive">{downloadError}</p>}
        </div>
      ) : null}
    </div>
  );

  return (
    <>
      <div
        className={cn(
          'hidden min-h-0 flex-col overflow-hidden bg-card lg:flex',
          LAYOUT_CLASSES[layout],
          className,
        )}
      >
        <div className="flex shrink-0 items-center gap-3 border-b border-border/70 px-4 py-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
              {getFileIcon(activeDoc.filename)}
            </span>
            <div className="flex min-w-0 flex-col">
              <span
                className="truncate text-sm font-semibold text-foreground"
                title={activeDoc.filename}
              >
                {activeDoc.filename}
              </span>
              <span className="text-xs text-muted-foreground">Preview</span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1">
            {documentNavigation}
            <Button
              variant="ghost-action"
              size="icon-sm"
              onClick={() => setExpanded(true)}
              title="Expand preview"
              aria-label="Expand preview"
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => void download()}
              title={activeDoc.source_url ? 'Open or download source' : 'Download'}
              aria-label={activeDoc.source_url ? 'Open or download source' : 'Download document'}
            >
              <Download className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setCollapsed(true)}
              title="Collapse preview"
              aria-label="Collapse preview"
            >
              <PanelRightClose className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {downloadError && (
          <div className="flex shrink-0 items-center gap-2 border-b border-border bg-destructive/5 px-4 py-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {downloadError}
          </div>
        )}
        {!expanded && previewBody}
      </div>

      <Dialog.Root open={expanded} onOpenChange={setExpanded}>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-[70] bg-black/45 backdrop-blur-sm transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0" />
          <Dialog.Popup className="fixed inset-3 z-[71] flex min-h-0 flex-col overflow-hidden rounded-xl bg-card text-card-foreground shadow-2xl outline-none transition duration-150 data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 sm:inset-5 lg:inset-8">
            <div className="flex shrink-0 items-center gap-4 border-b border-border/70 px-4 py-3 sm:px-5">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                  {getFileIcon(activeDoc.filename)}
                </span>
                <div className="min-w-0">
                  <Dialog.Title className="truncate text-sm font-semibold text-foreground sm:text-base">
                    {activeDoc.filename}
                  </Dialog.Title>
                  <Dialog.Description className="text-xs text-muted-foreground">
                    Document preview
                  </Dialog.Description>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-1.5">
                {documentNavigation}
                <Button
                  variant="ghost"
                  size="icon-lg"
                  onClick={() => void download()}
                  title="Download"
                  aria-label="Download document"
                >
                  <Download className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-lg"
                  onClick={() => setExpanded(false)}
                  title="Close expanded preview"
                  aria-label="Close expanded preview"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
            {downloadError && (
              <div className="flex shrink-0 items-center gap-2 border-b border-border bg-destructive/5 px-5 py-2 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {downloadError}
              </div>
            )}
            {expanded && previewBody}
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
