import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { PipelineListEntity, PipelineSchemaField } from '@/shared/types/pipeline';
import {
  deriveExportFields,
  defaultSelectedKeys,
  orderSelectedFields,
  buildExportRows,
  buildExportFilename,
} from '@/lib/export/fields';
import { exportToCsv } from '@/lib/export/formatters/csv';
import { triggerDownload } from '@/lib/export/download';

interface ExportCsvButtonProps {
  entities: PipelineListEntity[];
  schemaFields: PipelineSchemaField[];
  workflowName: string;
}

/** Single-click CSV export using the default field selection — a minimal,
 *  format-less alternative to `ExportDropdown` for skins that don't want the
 *  multi-format field-picker flow. */
export default function ExportCsvButton({ entities, schemaFields, workflowName }: ExportCsvButtonProps) {
  function handleExport() {
    const fields = deriveExportFields(entities, schemaFields);
    const selected = orderSelectedFields(fields, defaultSelectedKeys(fields));
    const rows = buildExportRows(entities, selected);
    const blob = exportToCsv(rows, selected);
    triggerDownload(blob, buildExportFilename(workflowName, 'csv'));
  }

  return (
    <Button variant="outline" size="md" rounded="lg" icon={<Download className="h-4 w-4" />} onClick={handleExport}>
      Export CSV
    </Button>
  );
}
