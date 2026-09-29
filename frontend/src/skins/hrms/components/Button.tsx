import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-cobalt text-white hover:bg-cobalt/90",
  secondary: "bg-white text-cobalt border border-cobalt hover:bg-cobalt/5",
  ghost: "bg-transparent text-gray-600 hover:bg-gray-50",
  danger: "bg-danger text-white hover:bg-danger/90",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium
        transition-colors duration-hover ease-brand disabled:cursor-not-allowed disabled:opacity-50
        ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    />
  );
}
