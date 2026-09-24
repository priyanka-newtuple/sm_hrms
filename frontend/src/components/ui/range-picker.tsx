"use client"

import { format } from "date-fns"
import { CalendarIcon } from "lucide-react"
import { type DateRange } from "react-day-picker"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calender"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

export interface DatePickerWithRangeProps {
  /** Controlled selected range. */
  value?: DateRange
  /** Fires whenever the selected range changes (undefined when cleared). */
  onChange?: (range: DateRange | undefined) => void
  /** Label shown on the trigger when no range is selected. */
  placeholder?: string
  /** Extra classes for the trigger button. */
  className?: string
}

/**
 * Controlled two-month date-range picker. Trigger renders as the design-system
 * Button via Base UI's `render` prop (this project's Popover/Button are Base UI,
 * which compose with `render`, not Radix's `asChild`).
 */
export function DatePickerWithRange({
  value,
  onChange,
  placeholder = "Pick a date range",
  className,
}: DatePickerWithRangeProps) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className={cn("justify-start px-2.5 font-normal", className)}
          >
            <CalendarIcon />
            {value?.from ? (
              value.to ? (
                <>
                  {format(value.from, "LLL dd, y")} - {format(value.to, "LLL dd, y")}
                </>
              ) : (
                format(value.from, "LLL dd, y")
              )
            ) : (
              <span>{placeholder}</span>
            )}
          </Button>
        }
      />
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          defaultMonth={value?.from}
          selected={value}
          onSelect={onChange}
          numberOfMonths={2}
        />
      </PopoverContent>
    </Popover>
  )
}
