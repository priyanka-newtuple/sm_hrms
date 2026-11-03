import type { ReactNode } from 'react';

/** Presentation only: callers pass the native field requirement, never infer it from a name. */
export function FieldLabel({children, required = false}: {children: ReactNode; required?: boolean}) {
  return <span>{children}{required && <span aria-hidden="true" title="Required" className="ml-1 text-red-700">*</span>}</span>;
}
