/** Copies another row's items onto the active row. */

import { ChevronDown, Copy } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { pillClass, type Row } from './rows';

type CopyFromMenuProps = {
  options: Row[];
  disabled: boolean;
  onCopy: (toggles: string[]) => void;
};

export default function CopyFromMenu({ options, disabled, onCopy }: CopyFromMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled || options.length === 0}
        className={cn(pillClass, 'inline-flex items-center gap-1.5 whitespace-nowrap')}
      >
        <Copy size={13} />
        Copy from
        <ChevronDown size={12} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {options.map((row) => (
          <DropdownMenuItem key={row.dropdown} onClick={() => onCopy(row.toggles)}>
            <span className="min-w-0 flex-1 truncate">{row.dropdown}</span>
            <span className="text-xs font-semibold text-cobalt">{row.toggles.length}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
