import { Plus } from "lucide-react";
import { cn } from "../../lib/cn";

/** Botão de ação flutuante — Imagem 5, canto inferior direito. */
export function Fab({
  onClick,
  label,
  className,
}: {
  onClick: () => void;
  label: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "fixed right-6 bottom-6 z-30 flex h-14 w-14 items-center justify-center",
        "rounded-full bg-brand-700 text-white shadow-lg shadow-brand-900/20",
        "transition-transform hover:bg-brand-800 active:scale-95",
        className
      )}
    >
      <Plus aria-hidden="true" className="h-6 w-6" strokeWidth={2.5} />
    </button>
  );
}