import type { ReactNode } from 'react';
import { CalendarClock } from 'lucide-react';

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

export function AutomationSurface({
  embedded,
  open,
  onOpenChange,
  children,
}: {
  embedded: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  if (embedded) {
    return <div className="rounded-2xl border border-border bg-background shadow-sm">{children}</div>;
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">{children}</SheetContent>
    </Sheet>
  );
}

export function AutomationHeader({ embedded, description }: { embedded: boolean; description: string }) {
  if (embedded) {
    return (
      <div className="border-b border-border px-5 py-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <CalendarClock className="h-5 w-5" /> Workflow automations
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
    );
  }
  return (
    <SheetHeader className="border-b border-border">
      <SheetTitle className="flex items-center gap-2">
        <CalendarClock className="h-5 w-5" /> Workflow automations
      </SheetTitle>
      <SheetDescription>{description}</SheetDescription>
    </SheetHeader>
  );
}
