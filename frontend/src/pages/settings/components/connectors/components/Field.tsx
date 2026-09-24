import type { ReactNode } from 'react';

/** Shared input style for connector form controls. */
export const inputClass = 'h-9 w-full rounded-md border border-input bg-background px-3 text-sm';

/** Labelled field wrapper used across the connector form. */
export default function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium">{label}</span>
      {children}
    </label>
  );
}
