import { cn } from "../../lib/cn";
import { initials } from "../../lib/format";

const sizeClasses = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-16 w-16 text-xl",
} as const;

export function Avatar({
  label,
  size = "md",
  tone = "brand",
  className,
}: {
  label: string;
  size?: keyof typeof sizeClasses;
  tone?: "brand" | "neutral";
  className?: string;
}) {
  const toneClass =
    tone === "brand"
      ? "bg-brand-100 text-brand-800"
      : "bg-slate-200 text-slate-600";

  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-bold",
        sizeClasses[size],
        toneClass,
        className
      )}
    >
      {initials(label)}
    </span>
  );
}