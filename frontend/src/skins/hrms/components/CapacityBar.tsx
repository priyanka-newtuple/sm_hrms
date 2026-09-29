/**
 * Committed allocation for one employee. Segments past 100% render amber —
 * over-allocation is permitted by policy, so it's surfaced rather than blocked.
 */
export function CapacityBar({
  percent,
  label,
}: {
  percent: number;
  label?: string;
}) {
  const over = percent > 100;
  // Scale the bar so 100% fills it; anything beyond overflows into the amber tail.
  const withinWidth = Math.min(percent, 100);
  const overWidth = over ? Math.min(percent - 100, 100) : 0;

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-gray-600">{label ?? "Committed"}</span>
        <span className={over ? "font-semibold text-warning" : "font-semibold text-gray-900"}>
          {percent}%{over && " — over-allocated"}
        </span>
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-gray-50">
        <div
          className={`h-full transition-all duration-transition ease-brand ${
            over ? "bg-warning" : "bg-cobalt"
          }`}
          style={{ width: `${withinWidth}%` }}
        />
        {overWidth > 0 && (
          <div
            className="h-full bg-warning/50 transition-all duration-transition ease-brand"
            style={{ width: `${overWidth}%` }}
          />
        )}
      </div>
    </div>
  );
}
