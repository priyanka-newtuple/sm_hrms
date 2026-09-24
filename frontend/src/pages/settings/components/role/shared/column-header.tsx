import { type ReactNode } from "react"

/**
 * Centers a DataTable column header — for the narrow action/toggle columns in
 * the permission-matrix tables (Entity Access, Permissions, Forms), which sit
 * under a centered cell. Inherits TableHead's own type styles otherwise.
 */
export function ColumnHeaderLabel({ children }: { children: ReactNode }) {
  return <div className="w-full text-center">{children}</div>
}
