import { useCallback, useEffect, useRef, useState } from 'react';
import { File, FileSpreadsheet, FileText } from 'lucide-react';
import '@js-preview/excel/lib/index.css';
import { documents } from '../services/api';
import type { DownloadUrlResult } from '../services/api/documents';
import type { DocumentMetadata } from '../types';

// CSV is intentionally excluded — it renders fine inline as text, and
// @js-preview/excel/ExcelJS only parse xls/xlsx.
const EXCEL_EXTENSIONS = ['xlsx', 'xls', 'xlsm', 'xlsb'];
const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

// Word docs are rendered inline via docx-preview. Only OOXML `.docx` is supported —
// legacy binary `.doc` is not, and falls through to the no-preview placeholder.
const WORD_EXTENSIONS = ['docx'];

// Types a browser can safely render inline in an <iframe>. This is an ALLOWLIST on
// purpose: anything not listed here (and not handled as csv/excel/word) has no inline
// preview and must NOT be loaded into an iframe — a blob whose content-type the browser
// can't display (e.g. .doc, .ppt) is auto-downloaded instead of shown (STAT-409).
const IFRAME_EXTENSIONS = [
  'pdf',
  'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp',
  'txt', 'md', 'json', 'log', 'html', 'htm',
];

export function getFileExtension(filename: string): string {
  return filename.split('.').pop()?.toLowerCase() ?? '';
}

// Get icon based on file extension. Lives here (not in a component file) so
// react-refresh's only-export-components rule stays happy.
export function getFileIcon(filename: string) {
  const ext = getFileExtension(filename);
  switch (ext) {
    case 'pdf':
      return <FileText className="w-4 h-4 text-destructive" />;
    case 'doc':
    case 'docx':
      return <FileText className="w-4 h-4 text-info" />;
    case 'xlsx':
    case 'xls':
    case 'xlsm':
    case 'xlsb':
    case 'csv':
      return <FileSpreadsheet className="w-4 h-4 text-success" />;
    case 'txt':
      return <File className="w-4 h-4 text-muted-foreground" />;
    default:
      return <File className="w-4 h-4 text-muted-foreground" />;
  }
}

function isExcelFile(filename: string): boolean {
  return EXCEL_EXTENSIONS.includes(getFileExtension(filename));
}

function isCsvFile(filename: string): boolean {
  return getFileExtension(filename) === 'csv';
}

function isWordFile(filename: string): boolean {
  return WORD_EXTENSIONS.includes(getFileExtension(filename));
}

function isIframePreviewable(filename: string): boolean {
  return IFRAME_EXTENSIONS.includes(getFileExtension(filename));
}

// Minimal RFC-4180 CSV parser (handles quoted fields, escaped quotes, and
// embedded commas/newlines). Browsers won't render text/csv inline, so we parse
// and display it ourselves.
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else { inQuotes = false; }
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else if (c !== '\r') {
      field += c;
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

// Convert binary .xls/.xlsb to .xlsx via SheetJS so the ZIP-based viewer can read them.
async function ensureZipXlsxBlob(blob: Blob, filename: string): Promise<Blob> {
  const ext = getFileExtension(filename);
  if (ext !== 'xls' && ext !== 'xlsb') return blob;
  try {
    const XLSX = await import('xlsx');
    const workbook = XLSX.read(await blob.arrayBuffer(), { type: 'array', cellStyles: true });
    const out = XLSX.write(workbook, { type: 'array', bookType: 'xlsx' }) as ArrayBuffer;
    return new Blob([out], { type: XLSX_MIME });
  } catch (e) {
    console.warn('Legacy spreadsheet → xlsx conversion failed, showing original:', e);
    return blob;
  }
}

// Reset hidden rows/columns, outline groups and row heights (kept from pivot
// exports) to a uniform height so nothing renders as a collapsed strip. Cell
// styles are preserved. Returns the original blob if anything fails.
async function normalizeExcelBlob(blob: Blob): Promise<Blob> {
  try {
    const { Workbook } = await import('exceljs');
    const workbook = new Workbook();
    await workbook.xlsx.load(await blob.arrayBuffer());
    workbook.eachSheet((sheet) => {
      sheet.eachRow({ includeEmpty: true }, (row) => {
        row.hidden = false;
        row.outlineLevel = 0;
        row.height = 20;
      });
      sheet.columns?.forEach((col) => {
        if (col) col.hidden = false;
      });
    });
    const buffer = await workbook.xlsx.writeBuffer();
    return new Blob([buffer], { type: XLSX_MIME });
  } catch (e) {
    console.warn('Excel normalization failed, showing original file:', e);
    return blob;
  }
}

export interface DocumentPreviewState {
  loading: boolean;
  error: string | null;
  blobUrl: string | null;
  csvRows: string[][] | null;
  excelBlob: Blob | null;
  excelRendering: boolean;
  /** Attach to the div that @js-preview/excel renders into. */
  excelContainerRef: React.RefCallback<HTMLDivElement>;
  wordBlob: Blob | null;
  wordRendering: boolean;
  /** Attach to the div that docx-preview renders into. */
  wordContainerRef: React.RefCallback<HTMLDivElement>;
  /** True when the file type has no inline preview (e.g. .doc, .ppt) — show a
   *  download-only placeholder instead of loading it into an iframe. */
  unsupported: boolean;
}

/**
 * Loads preview content for a document: CSV → parsed rows, Excel → normalized
 * blob for @js-preview/excel, Word (.docx) → docx-preview, other renderable types
 * (pdf/image/text) → URL for an iframe, everything else → no-preview placeholder.
 * Re-runs when the document changes; revokes blob URLs on change and unmount.
 */
export function useDocumentPreview(doc: DocumentMetadata | null): DocumentPreviewState {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [csvRows, setCsvRows] = useState<string[][] | null>(null);
  const [excelBlob, setExcelBlob] = useState<Blob | null>(null);
  const [excelRendering, setExcelRendering] = useState(false);
  const [excelContainer, setExcelContainer] = useState<HTMLDivElement | null>(null);
  const excelContainerRef = useCallback((container: HTMLDivElement | null) => {
    setExcelContainer(container);
  }, []);
  const [wordBlob, setWordBlob] = useState<Blob | null>(null);
  const [wordRendering, setWordRendering] = useState(false);
  const [wordContainer, setWordContainer] = useState<HTMLDivElement | null>(null);
  const wordContainerRef = useCallback((container: HTMLDivElement | null) => {
    setWordContainer(container);
  }, []);
  const [unsupported, setUnsupported] = useState(false);
  const blobUrlRef = useRef<string | null>(null);

  const docId = doc?.id ?? null;
  const filename = doc?.filename ?? '';
  const sourceUrl = doc?.source_url ?? null;

  useEffect(() => {
    const revoke = () => {
      if (blobUrlRef.current?.startsWith('blob:')) {
        URL.revokeObjectURL(blobUrlRef.current);
      }
      blobUrlRef.current = null;
    };

    setBlobUrl(null);
    setCsvRows(null);
    setExcelBlob(null);
    setExcelRendering(false);
    setWordBlob(null);
    setWordRendering(false);
    setUnsupported(false);
    setError(null);
    revoke();

    if (!docId) return;

    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        // Review-only remote references intentionally stay external until the
        // user confirms the import. Reuse the standard iframe preview chrome
        // without fetching or persisting bytes through the platform.
        if (sourceUrl) {
          if (!isIframePreviewable(filename)) {
            if (!cancelled) setUnsupported(true);
            return;
          }
          if (!cancelled) {
            blobUrlRef.current = sourceUrl;
            setBlobUrl(sourceUrl);
          }
          return;
        }

        // CSV is parsed and rendered as a table (browsers download text/csv).
        if (isCsvFile(filename)) {
          const { blob } = await documents.fetchContent(docId);
          const rows = parseCsv(await blob.text());
          if (!cancelled) setCsvRows(rows);
          return;
        }

        // Excel is handed to the viewer effect below rather than an iframe.
        if (isExcelFile(filename)) {
          const { blob } = await documents.fetchContent(docId);
          const zipReady = await ensureZipXlsxBlob(blob, filename);
          const normalized = await normalizeExcelBlob(zipReady);
          if (!cancelled) {
            setExcelRendering(true);
            setExcelBlob(normalized);
          }
          return;
        }

        // Word (.docx) is handed to the docx-preview viewer effect below.
        if (isWordFile(filename)) {
          const { blob } = await documents.fetchContent(docId);
          if (!cancelled) {
            setWordRendering(true);
            setWordBlob(blob);
          }
          return;
        }

        // No inline preview for this type (e.g. .doc, .ppt, unknown binaries).
        // Do NOT fetch it into an iframe — the browser would auto-download an
        // unrenderable blob (STAT-409). Show a download-only placeholder instead.
        if (!isIframePreviewable(filename)) {
          if (!cancelled) setUnsupported(true);
          return;
        }

        const { url, provider }: DownloadUrlResult = await documents.getDownloadUrl(docId);
        if (provider === 'azure') {
          if (!cancelled) {
            blobUrlRef.current = url;
            setBlobUrl(url);
          }
        } else {
          const { blob, contentType } = await documents.fetchContent(docId);
          const objUrl = URL.createObjectURL(new Blob([blob], { type: contentType }));
          if (cancelled) {
            URL.revokeObjectURL(objUrl);
            return;
          }
          blobUrlRef.current = objUrl;
          setBlobUrl(objUrl);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load preview');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      revoke();
    };
  }, [docId, filename, sourceUrl]);

  // Mount the Excel viewer once both the blob and its current host are ready.
  // The host changes when the preview moves between the dock and modal.
  useEffect(() => {
    if (!excelBlob || !excelContainer) return;

    let cancelled = false;
    let viewer: { preview: (b: Blob) => Promise<unknown>; destroy: () => void } | null = null;
    setExcelRendering(true);

    void (async () => {
      try {
        const { default: jsPreviewExcel } = await import('@js-preview/excel');
        if (cancelled) return;
        viewer = jsPreviewExcel.init(excelContainer);
        await viewer.preview(excelBlob);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render spreadsheet');
        }
      } finally {
        if (!cancelled) setExcelRendering(false);
      }
    })();

    return () => {
      cancelled = true;
      viewer?.destroy();
    };
  }, [excelBlob, excelContainer]);

  // Render the .docx into its host once both the blob and container are ready.
  // Mirrors the Excel viewer: lazy-import keeps docx-preview out of the main bundle.
  useEffect(() => {
    if (!wordBlob || !wordContainer) return;

    let cancelled = false;
    setWordRendering(true);

    void (async () => {
      try {
        const { renderAsync } = await import('docx-preview');
        if (cancelled) return;
        wordContainer.innerHTML = '';
        await renderAsync(wordBlob, wordContainer, undefined, {
          className: 'docx',
          inWrapper: true,
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render document');
        }
      } finally {
        if (!cancelled) setWordRendering(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [wordBlob, wordContainer]);

  return {
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
  };
}
