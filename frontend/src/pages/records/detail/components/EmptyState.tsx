import { Database, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { displayEntityType } from '../helpers';

interface EmptyStateProps {
  routeEntityType: string;
  hasMachines: boolean;
  hasSchemas: boolean;
  onCreate: () => void;
}

export default function EmptyState({
  routeEntityType,
  hasMachines,
  hasSchemas,
  onCreate,
}: EmptyStateProps) {
  return (
    <div className="bg-card rounded-xl border border-border p-12 text-center">
      <Database className="w-12 h-12 text-muted-foreground/60 mx-auto mb-3" />
      <p className="text-muted-foreground font-medium mb-1">No entities yet</p>
      <p className="text-sm text-muted-foreground mb-4">
        {!hasMachines
          ? routeEntityType
            ? `Create a form for ${displayEntityType(routeEntityType)} to start adding records.`
            : 'Create a form first, then come back to add entities.'
          : routeEntityType
            ? `Create your first ${displayEntityType(routeEntityType)} using one of your state machines.`
            : 'Create your first entity using a form and, optionally, a workflow.'}
      </p>
      {hasSchemas && (
        <Button variant="ghost" onClick={onCreate} icon={<Plus className="w-4 h-4" />}>
          {routeEntityType ? `Add ${displayEntityType(routeEntityType)}` : 'Create Entity'}
        </Button>
      )}
    </div>
  );
}
