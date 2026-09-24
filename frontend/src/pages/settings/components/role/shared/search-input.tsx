import { SearchIcon } from "./icons"

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Search...",
  className = "w-[280px]",
}: SearchInputProps) {
  return (
    <div className={`relative ${className}`}>
      <span className="absolute left-[11px] top-1/2 -translate-y-1/2 flex text-muted-foreground">
        <SearchIcon width={15} height={15} />
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-border bg-card px-[10px] py-2 pl-8 text-[13.5px] text-foreground outline-none transition-all placeholder:text-muted-foreground focus:border-ring focus:ring-[3px] focus:ring-ring/20"
      />
    </div>
  )
}
