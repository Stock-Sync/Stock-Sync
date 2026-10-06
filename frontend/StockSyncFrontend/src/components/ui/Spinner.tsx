import { Loader2 } from "lucide-react";
import { cn } from "../../lib/cn";

export function Spinner({
  className,
  label = "Carregando",
}: {
  className?: string;
  label?: string;
}) {
  return (
    <span role="status" aria-label={label} className={cn("inline-flex", className)}>
      <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-brand-600" />
    </span>
  );
}

/** Estado de carregamento para blocos de conteúdo. */
export function LoadingBlock({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 px-6 py-14">
      <Spinner />
      <span className="text-sm text-slate-500">
        {label ?? "Carregando..."}
      </span>
    </div>
  );
}