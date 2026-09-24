import { cn } from "@/lib/utils"

interface ColorToggleProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  color?: string
  disabled?: boolean
}

export function ColorToggle({
  checked,
  onCheckedChange,
  color = "#4F46E5",
  disabled = false,
}: ColorToggleProps) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative w-[38px] h-[22px] rounded-full border-none cursor-pointer transition-colors p-0 flex-shrink-0",
        disabled && "opacity-40 cursor-not-allowed"
      )}
      style={{
        backgroundColor: checked ? color : "var(--input)",
      }}
    >
      <span
        className="absolute top-[2px] left-[2px] w-[18px] h-[18px] rounded-full bg-card shadow-[0_1px_2px_rgba(0,0,0,0.25)] transition-transform"
        style={{
          transform: checked ? "translateX(16px)" : "translateX(0)",
        }}
      />
    </button>
  )
}
