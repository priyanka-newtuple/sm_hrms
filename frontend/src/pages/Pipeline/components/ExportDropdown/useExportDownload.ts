import { useState } from 'react';
import { toast } from 'sonner';
import type { PipelineListEntity } from '@/shared/types/pipeline';
import type { ExportField, ExportFormat } from '@/lib/export/types';
import { buildExportRows, buildExportFilename } from '@/lib/export/fields';
import { triggerDownload } from '@/lib/export/download';
import { exportToCsv } from '@/lib/export/formatters/csv';
import { exportToJson } from '@/lib/export/formatters/json';

interface RunExportOptions {
  format: ExportFormat;
  entities: PipelineListEntity[];
  fields: ExportField[];
  workflowName: string;
}

/** Orchestrates building rows, formatting, and downloading. */
export function useExportDownload() {
  const [isExporting, setIsExporting] = useState(false);

  async function runExport({ format, entities, fields, workflowName }: RunExportOptions) {
    if (entities.length === 0 || fields.length === 0) {
      toast.error('Nothing to export', {
        description: 'Select at least one field and ensure there are rows to export.',
      });
      return;
    }
    setIsExporting(true);
    try {
      // Yield once so the "Exporting…" state paints before potentially heavy
      // synchronous formatting on large datasets.
      await new Promise((resolve) => setTimeout(resolve, 0));
      const rows = buildExportRows(entities, fields);
      const filename = buildExportFilename(workflowName, format);
      let blob: Blob;
      if (format === 'csv') {
        blob = exportToCsv(rows, fields);
      } else if (format === 'json') {
        blob = exportToJson(rows, fields);
      } else if (format === 'xlsx') {
        // SheetJS is heavy — load only when actually exporting an Excel file.
        const { exportToXlsx } = await import('@/lib/export/formatters/xlsx');
        blob = exportToXlsx(rows, fields);
      } else {
        // PDF deps are heavy — load only when actually exporting a PDF.
        const { exportToPdf } = await import('@/lib/export/formatters/pdf');
        blob = exportToPdf(rows, fields, workflowName);
      }
      triggerDownload(blob, filename);
    } catch (err) {
      toast.error('Export failed', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setIsExporting(false);
    }
  }

  return { isExporting, runExport };
}
