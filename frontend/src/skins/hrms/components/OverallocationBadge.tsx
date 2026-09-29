import type { Allocation } from "@/skins/hrms/api/types";

export function OverallocationBadge({ allocation }: { allocation: Allocation }) {
  if (!allocation.over_allocated) return null;
  return <div className="mt-1 rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-800">
    <strong>Overallocated · {allocation.total_allocation_percent}% peak</strong>
    {allocation.overallocated_periods?.map(p => <div key={p.start_date}>
      {p.start_date} to {p.end_date ?? "ongoing"}: {p.total_allocation_percent}% (+{p.excess_percent}%)
    </div>)}
  </div>;
}
