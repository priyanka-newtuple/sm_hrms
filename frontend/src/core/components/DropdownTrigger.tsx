import { forwardRef, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { Button, type ButtonProps } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface DropdownTriggerProps extends Omit<ButtonProps, 'icon' | 'iconPosition' | 'children'> {
  icon?: ReactNode;
  label: ReactNode;
  isOpen?: boolean;
  hideChevron?: boolean;
  chevronClassName?: string;
}

const DropdownTrigger = forwardRef<HTMLButtonElement, DropdownTriggerProps>(
  ({ icon, label, isOpen, hideChevron, chevronClassName, className, variant = 'ghost', ...props }, ref) => {
    return (
      <Button
        ref={ref}
        variant={variant}
        {...props}
        className={cn('flex items-center gap-2 min-w-0', className)}
      >
        {icon}
        <span className="block min-w-0 flex-1 truncate text-left">{label}</span>
        {!hideChevron && (
          <ChevronDown
            className={cn(
              'w-4 h-4 shrink-0 transition-transform',
              isOpen && 'rotate-180',
              chevronClassName,
            )}
          />
        )}
      </Button>
    );
  },
);

DropdownTrigger.displayName = 'DropdownTrigger';

export default DropdownTrigger;
export type { DropdownTriggerProps };
