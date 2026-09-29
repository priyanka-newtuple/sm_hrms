import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const CONTROL =
  "w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-900 " +
  "transition-colors duration-hover ease-brand focus:border-cobalt focus:outline-none " +
  "disabled:bg-gray-50 disabled:text-gray-600";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-gray-600">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-600">{hint}</span>}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} ${props.className ?? ""}`} />;
}

export function Select({
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...props} className={`${CONTROL} ${props.className ?? ""}`}>
      {children}
    </select>
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={`${CONTROL} ${props.className ?? ""}`} />;
}

export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
      {message}
    </div>
  );
}

/** Amber, not red: over-allocation is allowed, just worth knowing about. */
export function WarningBanner({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-warning/40 bg-warning/5 px-3 py-2 text-sm">
      <div className="font-medium text-warning">{title}</div>
      {children && <div className="mt-1 text-gray-600">{children}</div>}
    </div>
  );
}

export function FormActions({ children }: { children: ReactNode }) {
  return <div className="flex justify-end gap-2 pt-2">{children}</div>;
}
