import { FileSpreadsheet, Sheet, FileJson, FileText, type LucideIcon } from 'lucide-react';
import type { ExportFormat } from '@/lib/export/types';

export interface FormatMeta {
  label: string;
  description: string;
  icon: LucideIcon;
}

/** Display metadata for each export format, shared by the menu and slide-over. */
export const FORMAT_META: Record<ExportFormat, FormatMeta> = {
  csv: {
    label: 'CSV',
    description: 'Plain text, opens anywhere',
    icon: FileSpreadsheet,
  },
  xlsx: {
    label: 'Excel',
    description: 'Native .xlsx workbook',
    icon: Sheet,
  },
  json: {
    label: 'JSON',
    description: 'Structured data for developers',
    icon: FileJson,
  },
  pdf: {
    label: 'PDF',
    description: 'Printable table document',
    icon: FileText,
  },
};

export const FORMAT_ORDER: ExportFormat[] = ['csv', 'xlsx', 'json', 'pdf'];
