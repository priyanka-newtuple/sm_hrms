import { Database } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface RecordsEmptyStateProps {
  onGoToSettings: () => void;
}

export default function RecordsEmptyState({ onGoToSettings }: RecordsEmptyStateProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-12 text-center">
      <Database className="w-12 h-12 text-muted-foreground/40 mx-auto mb-3" />
      <p className="text-foreground font-medium mb-1">No entity types yet</p>
      <p className="text-sm text-muted-foreground mb-4">
        Create an entity type in Settings to start adding records.
      </p>
      <Button variant="primary" onClick={onGoToSettings}>Go to Settings</Button>
    </div>
  );
}
