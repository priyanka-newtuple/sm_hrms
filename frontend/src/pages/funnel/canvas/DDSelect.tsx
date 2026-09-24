import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Check, ChevronDown } from "lucide-react";

interface DDSelectProps {
  value: string | undefined;
  placeholder?: string;
  options: { value: string; label: React.ReactNode }[];
  onSelect: (v: string) => void;
  className?: string;
}

export function DDSelect({ value, placeholder, options, onSelect, className }: DDSelectProps) {
  const current = options.find((o) => o.value === value);
  const triggerTitle = typeof current?.label === "string" ? current.label : (value ?? "");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        title={triggerTitle}
        className={`flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50${className ? ` ${className}` : ""}`}
      >
        <span className="truncate">{current ? current.label : (placeholder ?? "Select…")}</span>
        <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-64 overflow-y-auto">
        {options.map((opt) => {
          const isSelected = opt.value === value;
          return (
            <DropdownMenuItem
              key={opt.value}
              onClick={() => onSelect(opt.value)}
              className={isSelected ? "bg-accent font-medium" : ""}
            >
              <span className="flex-1">{opt.label}</span>
              {isSelected && <Check className="ml-2 h-3.5 w-3.5 shrink-0 text-foreground" />}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
