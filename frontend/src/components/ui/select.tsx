import * as React from "react";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";

type SelectCtx = {
  value: string;
  onValueChange: (v: string) => void;
  open: boolean;
  setOpen: (o: boolean) => void;
  getLabel: (v: string) => React.ReactNode;
  registerItem: (value: string, label: React.ReactNode) => void;
};

const SelectContext = React.createContext<SelectCtx | null>(null);

function useSelectContext(): SelectCtx {
  const ctx = React.useContext(SelectContext);
  if (!ctx) throw new Error("Select.* must be used inside <Select>");
  return ctx;
}

interface SelectProps {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  children?: React.ReactNode;
}

export function Select({ value: controlled, defaultValue = "", onValueChange, children }: SelectProps) {
  const [internal, setInternal] = React.useState(defaultValue);
  const value = controlled ?? internal;
  const [open, setOpen] = React.useState(false);
  const itemsRef = React.useRef<Map<string, React.ReactNode>>(new Map());

  const registerItem = React.useCallback((val: string, label: React.ReactNode) => {
    itemsRef.current.set(val, label);
  }, []);

  const getLabel = React.useCallback((val: string): React.ReactNode => {
    return itemsRef.current.get(val);
  }, []);

  const handleChange = React.useCallback(
    (v: string) => {
      if (controlled === undefined) setInternal(v);
      onValueChange?.(v);
      setOpen(false);
    },
    [controlled, onValueChange],
  );

  const ctxValue = React.useMemo<SelectCtx>(
    () => ({ value, onValueChange: handleChange, open, setOpen, getLabel, registerItem }),
    [value, handleChange, open, getLabel, registerItem],
  );

  return <SelectContext.Provider value={ctxValue}>{children}</SelectContext.Provider>;
}

interface SelectTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

export const SelectTrigger = React.forwardRef<HTMLButtonElement, SelectTriggerProps>(
  ({ className, children, ...props }, ref) => {
    const ctx = useSelectContext();
    const triggerRef = React.useRef<HTMLButtonElement | null>(null);
    React.useImperativeHandle(ref, () => triggerRef.current as HTMLButtonElement);

    React.useEffect(() => {
      if (!ctx.open) return;
      function handleClick(e: MouseEvent) {
        const target = e.target as Node;
        if (triggerRef.current && triggerRef.current.contains(target)) return;
        const content = document.querySelector('[data-select-content="true"]');
        if (content && content.contains(target)) return;
        ctx.setOpen(false);
      }
      document.addEventListener("mousedown", handleClick);
      return () => document.removeEventListener("mousedown", handleClick);
    }, [ctx]);

    return (
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={ctx.open}
        onClick={() => ctx.setOpen(!ctx.open)}
        className={cn(
          "flex h-9 w-full items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-sm shadow-sm",
          "focus:outline-none focus:ring-2 focus:ring-cobalt/30 focus:border-cobalt",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
        <ChevronDown className="h-4 w-4 opacity-50 ml-2 shrink-0" />
      </button>
    );
  },
);
SelectTrigger.displayName = "SelectTrigger";

interface SelectValueProps {
  placeholder?: string;
  className?: string;
}

export function SelectValue({ placeholder, className }: SelectValueProps) {
  const ctx = useSelectContext();
  const label = ctx.getLabel(ctx.value);
  return (
    <span className={cn("truncate text-left flex-1", !label && "text-muted-foreground", className)}>
      {label ?? placeholder}
    </span>
  );
}

interface SelectContentProps extends React.HTMLAttributes<HTMLDivElement> {}

export function SelectContent({ className, children, ...props }: SelectContentProps) {
  const ctx = useSelectContext();
  if (!ctx.open) return null;
  return (
    <div
      data-select-content="true"
      role="listbox"
      className={cn(
        "relative z-50 mt-1 min-w-[8rem] overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-md",
        "max-h-60 overflow-y-auto",
        className,
      )}
      {...props}
    >
      <div className="p-1">{children}</div>
    </div>
  );
}

interface SelectItemProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "onSelect"> {
  value: string;
}

export function SelectItem({ value, className, children, ...props }: SelectItemProps) {
  const ctx = useSelectContext();

  React.useEffect(() => {
    ctx.registerItem(value, children);
  }, [ctx, value, children]);

  const selected = ctx.value === value;
  return (
    <div
      role="option"
      aria-selected={selected}
      onClick={() => ctx.onValueChange(value)}
      className={cn(
        "relative flex w-full cursor-pointer select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none",
        "hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground",
        className,
      )}
      {...props}
    >
      {selected && (
        <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
          <Check className="h-4 w-4" />
        </span>
      )}
      {children}
    </div>
  );
}
