import { ShieldOff } from 'lucide-react';

export interface AccessDeniedProps {
  entityType?: string;
  message?: string;
}

export default function AccessDenied({ entityType, message }: AccessDeniedProps) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <ShieldOff className="mb-4 h-10 w-10 text-muted-foreground/60" />
      <h2 className="mb-1 text-base font-semibold text-foreground">Access Denied</h2>
      <p className="text-sm text-muted-foreground">
        {message ?? (
          entityType
            ? `You don't have permission to view ${entityType} records.`
            : "You don't have permission to view this content."
        )}
      </p>
    </div>
  );
}
