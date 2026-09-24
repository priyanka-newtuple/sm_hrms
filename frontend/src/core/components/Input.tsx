/**
 * Input Component
 *
 * A modern input component with label, helper text, and error states.
 * Includes variants for text, textarea, and select.
 */

import {
  forwardRef,
  type InputHTMLAttributes,
  type TextareaHTMLAttributes,
  type SelectHTMLAttributes,
  type ReactNode,
} from 'react';
import { cn } from '../../lib/utils';

// Base styles shared across all input types
const baseInputStyles =
  'w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm text-foreground transition-all duration-200 placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

const errorStyles = 'border-destructive/40 focus:border-destructive focus:ring-destructive/20';

// Label component
interface LabelProps {
  children: ReactNode;
  htmlFor?: string;
  required?: boolean;
  className?: string;
}

export function Label({ children, htmlFor, required, className = '' }: LabelProps) {
  return (
    <label
      htmlFor={htmlFor}
      className={cn('mb-1.5 block text-sm font-medium text-foreground', className)}
    >
      {children}
      {required && <span className="ml-0.5 text-destructive">*</span>}
    </label>
  );
}

// Helper text component
interface HelperTextProps {
  children: ReactNode;
  error?: boolean;
  className?: string;
}

export function HelperText({ children, error, className = '' }: HelperTextProps) {
  return (
    <p className={cn('mt-1.5 text-sm', error ? 'text-destructive' : 'text-muted-foreground', className)}>
      {children}
    </p>
  );
}

// Text Input
interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      helperText,
      error,
      leftIcon,
      rightIcon,
      required,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || props.name;
    const hasError = !!error;

    return (
      <div className="w-full">
        {label && (
          <Label htmlFor={inputId} required={required}>
            {label}
          </Label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            required={required}
            className={cn(
              baseInputStyles,
              hasError && errorStyles,
              leftIcon && 'pl-10',
              rightIcon && 'pr-10',
              className,
            )}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
              {rightIcon}
            </div>
          )}
        </div>
        {(error || helperText) && (
          <HelperText error={hasError}>{error || helperText}</HelperText>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

// Textarea
interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    { label, helperText, error, required, className = '', id, ...props },
    ref
  ) => {
    const inputId = id || props.name;
    const hasError = !!error;

    return (
      <div className="w-full">
        {label && (
          <Label htmlFor={inputId} required={required}>
            {label}
          </Label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          required={required}
          className={cn(baseInputStyles, hasError && errorStyles, 'min-h-[100px] resize-y', className)}
          {...props}
        />
        {(error || helperText) && (
          <HelperText error={hasError}>{error || helperText}</HelperText>
        )}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';

// Select
interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  options: { value: string; label: string }[];
  placeholder?: string;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      helperText,
      error,
      options,
      placeholder,
      required,
      className = '',
      id,
      ...props
    },
    ref
  ) => {
    const inputId = id || props.name;
    const hasError = !!error;

    return (
      <div className="w-full">
        {label && (
          <Label htmlFor={inputId} required={required}>
            {label}
          </Label>
        )}
        <select
          ref={ref}
          id={inputId}
          required={required}
          className={cn(
            baseInputStyles,
            hasError && errorStyles,
            "appearance-none cursor-pointer bg-[url('data:image/svg+xml;charset=UTF-8,%3csvg%20xmlns%3d%22http%3a%2f%2fwww.w3.org%2f2000%2fsvg%22%20width%3d%2224%22%20height%3d%2224%22%20viewBox%3d%220%200%2024%2024%22%20fill%3d%22none%22%20stroke%3d%22%236b7280%22%20stroke-width%3d%222%22%20stroke-linecap%3d%22round%22%20stroke-linejoin%3d%22round%22%3e%3cpolyline%20points%3d%226%209%2012%2015%2018%209%22%3e%3c%2fpolyline%3e%3c%2fsvg%3e')] bg-[length:20px] bg-[right_12px_center] bg-no-repeat pr-10",
            className,
          )}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {(error || helperText) && (
          <HelperText error={hasError}>{error || helperText}</HelperText>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';

// FormField wrapper for custom content
interface FormFieldProps {
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  children: ReactNode;
  className?: string;
}

export function FormField({
  label,
  helperText,
  error,
  required,
  children,
  className = '',
}: FormFieldProps) {
  const hasError = !!error;

  return (
    <div className={cn('w-full', className)}>
      {label && <Label required={required}>{label}</Label>}
      {children}
      {(error || helperText) && (
        <HelperText error={hasError}>{error || helperText}</HelperText>
      )}
    </div>
  );
}

export default Input;
export { Textarea, Select };
export type { InputProps, TextareaProps, SelectProps };
