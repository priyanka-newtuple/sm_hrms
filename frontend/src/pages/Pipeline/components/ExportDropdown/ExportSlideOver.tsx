import { useMemo, useState } from 'react';

import { useQuery } from '@tanstack/react-query';
import { Download, Search } from 'lucide-react';

import SlideOver from '@/core/components/SlideOver';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { PipelineListEntity, PipelineSchemaField } from '@/shared/types/pipeline';
import type { ExportFormat } from '@/lib/export/types';

import { FORMAT_META } from './formatMeta';
import { useExportFields } from './useExportFields';
import { useExportDownload } from './useExportDownload';
import FieldGroup from './FieldGroup';

interface ExportSlideOverProps {
  open: boolean;
  format: ExportFormat;
  entities: PipelineListEntity[];
  schemaFields: PipelineSchemaField[];
  workflowName: string;
  fetchAllRows?: (dataFieldIds: string[]) => Promise<PipelineListEntity[]>;
  onClose: () => void;
}

export default function ExportSlideOver({
  open,
  format,
  entities,
  schemaFields,
  workflowName,
  fetchAllRows,
  onClose,
}: ExportSlideOverProps) {
  // Keyed on field contents, not array identity — else a re-render refetches.
  const dataFieldIds = useMemo(() => schemaFields.map((f) => f.field), [schemaFields]);
  const fieldSignature = dataFieldIds.join('|');

  const { data: loadedRows, isFetching: isLoadingRows } = useQuery({
    queryKey: ['export-rows', workflowName, fieldSignature],
    queryFn: () => fetchAllRows?.(dataFieldIds) ?? Promise.resolve([]),
    enabled: open && Boolean(fetchAllRows),
    // The current filter set isn't in the key, so never serve a cached answer.
    gcTime: 0,
    staleTime: 0,
    refetchOnMount: 'always',
  });

  const exportEntities = loadedRows ?? entities;
  const { systemFields, dataFields, isSelected, toggle, setMany, selectedFields } =
    useExportFields(exportEntities, schemaFields);
  const { isExporting, runExport } = useExportDownload();
  const [query, setQuery] = useState('');

  const meta = FORMAT_META[format];
  const Icon = meta.icon;
  const totalSelectable = systemFields.length + dataFields.length;
  const hasFields = totalSelectable > 0;
  const hasRows = exportEntities.length > 0;
  const canExport = hasRows && selectedFields.length > 0 && !isExporting && !isLoadingRows;

  const q = query.trim().toLowerCase();
  const matches = (f: { label: string }) => !q || f.label.toLowerCase().includes(q);
  const visibleSystem = systemFields.filter(matches);
  const visibleData = dataFields.filter(matches);
  const noMatches = q.length > 0 && visibleSystem.length === 0 && visibleData.length === 0;

  async function handleExport() {
    await runExport({ format, entities: exportEntities, fields: selectedFields, workflowName });
    onClose();
  }

  return (
    <SlideOver
      open={open}
      onClose={onClose}
      title={`Export as ${meta.label}`}
      subtitle={
        isLoadingRows
          ? 'Loading records…'
          : `${exportEntities.length.toLocaleString()} ${exportEntities.length === 1 ? 'record' : 'records'} · ${selectedFields.length} of ${totalSelectable} fields selected`
      }
      size="md"
      footer={
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs tabular-nums text-muted-foreground">
            {selectedFields.length} field{selectedFields.length === 1 ? '' : 's'} ·{' '}
            {entities.length} row{entities.length === 1 ? '' : 's'}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" rounded="lg" onClick={onClose} disabled={isExporting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              rounded="lg"
              icon={<Download className="h-4 w-4" />}
              onClick={handleExport}
              disabled={!canExport}
              loading={isExporting}
            >
              Export {meta.label}
            </Button>
          </div>
        </div>
      }
    >
      {!hasRows ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          There are no rows to export. Adjust your filters and try again.
        </p>
      ) : !hasFields ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No exportable fields were found for these rows.
        </p>
      ) : (
        <>
          {/* Format banner */}
          <div className="mb-4 flex items-center gap-3 rounded-xl border border-border bg-muted/40 p-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">{meta.label} export</p>
              <p className="truncate text-xs text-muted-foreground">{meta.description}</p>
            </div>
          </div>

          {/* Field search */}
          <div className="relative mb-4">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search fields…"
              className="pl-9"
              aria-label="Search fields"
            />
          </div>

          {noMatches ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No fields match “{query}”.
            </p>
          ) : (
            <>
              <FieldGroup
                title="System Fields"
                fields={visibleSystem}
                isSelected={isSelected}
                onToggle={toggle}
                onSelectAll={() => setMany(visibleSystem.map((f) => f.key), true)}
                onClear={() => setMany(visibleSystem.map((f) => f.key), false)}
              />
              <FieldGroup
                title="Data Fields"
                fields={visibleData}
                isSelected={isSelected}
                onToggle={toggle}
                onSelectAll={() => setMany(visibleData.map((f) => f.key), true)}
                onClear={() => setMany(visibleData.map((f) => f.key), false)}
              />
            </>
          )}
        </>
      )}
    </SlideOver>
  );
}
