import { useState } from 'react';
import { Download, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuGroup,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
import type { PipelineListEntity, PipelineSchemaField } from '@/shared/types/pipeline';
import type { ExportFormat } from '@/lib/export/types';
import { FORMAT_META, FORMAT_ORDER } from './formatMeta';
import ExportSlideOver from './ExportSlideOver';

interface ExportDropdownProps {
  entities: PipelineListEntity[];
  schemaFields: PipelineSchemaField[];
  workflowName: string;
  fetchAllRows?: (dataFieldIds: string[]) => Promise<PipelineListEntity[]>;
}

/** Header export control: a dropdown of formats that opens the field picker. */
export default function ExportDropdown({
  entities,
  schemaFields,
  workflowName,
  fetchAllRows,
}: ExportDropdownProps) {
  const [activeFormat, setActiveFormat] = useState<ExportFormat | null>(null);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="outline"
              size="md"
              rounded="lg"
              icon={<Download className="h-4 w-4" />}
            />
          }
        >
          Export
          <ChevronDown className="ml-0.5 h-4 w-4 opacity-60" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={8} className="w-72 p-1.5">
          <DropdownMenuGroup>
            <DropdownMenuLabel className="px-2 pt-1.5 pb-1 text-[11px] font-semibold uppercase tracking-wider">
              Export as
            </DropdownMenuLabel>
            {FORMAT_ORDER.map((format) => {
              const meta = FORMAT_META[format];
              const Icon = meta.icon;
              return (
                <DropdownMenuItem
                  key={format}
                  onClick={() => setActiveFormat(format)}
                  className="gap-3 rounded-lg px-2 py-2"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm font-semibold text-foreground">{meta.label}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {meta.description}
                    </span>
                  </span>
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {activeFormat && (
        <ExportSlideOver
          open
          format={activeFormat}
          entities={entities}
          schemaFields={schemaFields}
          workflowName={workflowName}
          fetchAllRows={fetchAllRows}
          onClose={() => setActiveFormat(null)}
        />
      )}
    </>
  );
}
