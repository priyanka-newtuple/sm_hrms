import { AlertCircle, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
}

export default function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="mb-4 p-4 bg-destructive-subtle border border-destructive/30 rounded-lg text-destructive flex items-center gap-2 text-sm">
      <AlertCircle className="w-4 h-4 flex-shrink-0" />
      {message}
      <Button variant="ghost" onClick={onDismiss} className="ml-auto">
        <X className="w-4 h-4" />
      </Button>
    </div>
  );
}
