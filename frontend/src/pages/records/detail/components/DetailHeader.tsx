import { Database, Plus, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { displayEntityType, pluralizeEntityType } from '../helpers';

interface DetailHeaderProps {
  routeEntityType: string;
  entityTypeLabel?: string;
  recordCount: number;
  canCreate: boolean;
  onCreate: () => void;
  onBulkImport?: () => void;
}

export default function DetailHeader({
  routeEntityType,
  entityTypeLabel,
  recordCount,
  canCreate,
  onCreate,
  onBulkImport,
}: DetailHeaderProps) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-cobalt/10 flex items-center justify-center">
          <Database className="w-5 h-5 text-cobalt" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {routeEntityType
              ? pluralizeEntityType(entityTypeLabel || displayEntityType(routeEntityType))
              : 'Entities'}
          </h1>
          <p className="text-sm text-muted-foreground">{recordCount} total records</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {onBulkImport && (
          <Button variant="outline" onClick={onBulkImport} icon={<UploadCloud />}>
            Bulk import
          </Button>
        )}
        <Button variant="primary"
          onClick={onCreate}
          disabled={!canCreate}
          icon={<Plus className="w-4 h-4" />}
          title={!canCreate ? 'No forms available' : undefined}
        >
          {routeEntityType
            ? `Add ${entityTypeLabel || displayEntityType(routeEntityType)}`
            : 'Create Entity'}
        </Button>
      </div>
    </div>
  );
}
