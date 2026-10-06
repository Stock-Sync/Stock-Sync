import type { TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";
import { controlClasses, invalidControlClasses } from "./control-styles";
import { FieldError, Label } from "./Input";

export interface TextareaProps
  extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
}

export function Textarea({
  label,
  error,
  id,
  className,
  ...rest
}: TextareaProps) {
  const fieldId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div>
      <Label label={label} htmlFor={fieldId} />
      <textarea
        id={fieldId}
        rows={4}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${fieldId}-error` : undefined}
        className={cn(
          controlClasses,
          "resize-y",
          error && invalidControlClasses,
          className
        )}
        {...rest}
      />
      <FieldError id={`${fieldId}-error`} error={error} />
    </div>
  );
}