import type { InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";
import { controlClasses, invalidControlClasses } from "./control-styles";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function Label({
  label,
  htmlFor,
}: {
  label: string;
  htmlFor: string;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-1.5 block text-sm font-medium text-slate-700"
    >
      {label}
    </label>
  );
}

export function FieldError({ id, error }: { id: string; error?: string }) {
  if (!error) {
    return null;
  }
  return (
    <p id={id} role="alert" className="mt-1.5 text-xs font-medium text-red-600">
      {error}
    </p>
  );
}

export function Input({
  label,
  error,
  hint,
  id,
  className,
  ...rest
}: InputProps) {
  const inputId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div>
      <Label label={label} htmlFor={inputId} />
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${inputId}-error` : undefined}
        className={cn(
          controlClasses,
          error && invalidControlClasses,
          className
        )}
        {...rest}
      />
      {hint && !error && (
        <p className="mt-1.5 text-xs text-slate-500">{hint}</p>
      )}
      <FieldError id={`${inputId}-error`} error={error} />
    </div>
  );
}