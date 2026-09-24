import { type ReactNode } from "react"

interface FormFieldProps {
  label: string
  required?: boolean
  hint?: string
  children: ReactNode
}

export function FormField({ label, required, hint, children }: FormFieldProps) {
  return (
    <div className="mb-[22px]">
      <label className="block text-[13.5px] font-semibold mb-2">
        {label}
        {required && <span className="text-destructive ml-[3px]">*</span>}
      </label>
      {hint && (
        <div className="text-[12.5px] text-muted-foreground mb-[9px] -mt-1">
          {hint}
        </div>
      )}
      {children}
    </div>
  )
}

export function Divider() {
  return <div className="h-px bg-border my-[4px_0_22px]" style={{ margin: "4px 0 22px" }} />
}
