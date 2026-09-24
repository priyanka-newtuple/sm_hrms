import type { ReactNode } from 'react';
import { useAppLabels } from '@/shared/hooks';

export default function RecordsHeader({ action }: { action?: ReactNode }) {
  const appLabels = useAppLabels();
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">{appLabels.records}</h1>
        <p className="mt-1 text-sm text-muted-foreground max-w-2xl">
          Browse every entity in this workspace. Open one to view, create, or edit its records.
        </p>
      </div>
      {action}
    </div>
  );
}
