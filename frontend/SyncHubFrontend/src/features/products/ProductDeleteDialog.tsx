import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ExternalLink,
  Loader2,
  PauseCircle,
  Trash2,
  Unlink,
} from "lucide-react";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/toast-context";
import type { ProductDeletionConflictDetails } from "../../lib/api/catalog-client";
import { ApiError } from "../../types/api";
import type { ProductView } from "../../types/view-models";
import {
  useDeleteProduct,
  usePauseAndZeroListings,
  useUnbindProductListings,
} from "./queries";

type ResolutionAction = "pause" | "unbind" | "pause-unbind";

function isDeletionConflict(
  error: unknown
): error is ApiError & { details: ProductDeletionConflictDetails } {
  if (!(error instanceof ApiError)) {
    return false;
  }
  if (
    error.status !== 409 ||
    error.code !== "product_has_active_listings" ||
    !error.details ||
    typeof error.details !== "object"
  ) {
    return false;
  }
  const details = error.details as ProductDeletionConflictDetails;
  return Array.isArray(details.listings);
}

function statusLabel(status: string | null): string {
  switch (status) {
    case "active":
      return "Ativo";
    case "paused":
      return "Pausado";
    case "closed":
      return "Encerrado";
    default:
      return "Desconhecido";
  }
}

/**
 * Diálogo de exclusão de produto (Plan 10).
 *
 * Primeiro pede confirmação. Se o catálogo responder ``409
 * product_has_active_listings``, troca para o diálogo de resolução com as
 * ações de pausar/zerar, desvincular, combinar as duas ou abrir o anúncio.
 * Qualquer falha remota aborta a exclusão e mantém o produto intacto.
 */
export function ProductDeleteDialog({
  product,
  onClose,
  onDeleted,
}: {
  product: ProductView | null;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const { notify } = useToast();
  const deleteProduct = useDeleteProduct();
  const pauseAndZero = usePauseAndZeroListings();
  const unbindListings = useUnbindProductListings();

  const [conflict, setConflict] =
    useState<ProductDeletionConflictDetails | null>(null);
  const [action, setAction] = useState<ResolutionAction | null>(null);

  useEffect(() => {
    if (!conflict) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && action === null) {
        onClose();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [conflict, action, onClose]);

  if (!product) {
    return null;
  }

  const busy =
    deleteProduct.isPending ||
    pauseAndZero.isPending ||
    unbindListings.isPending ||
    action !== null;

  const finishDeletion = async () => {
    await deleteProduct.mutateAsync(product);
    notify({
      tone: "success",
      title: "Produto removido",
      description: product.title,
    });
    onDeleted();
  };

  const handleInitialDelete = async () => {
    try {
      await finishDeletion();
    } catch (error) {
      if (isDeletionConflict(error)) {
        setConflict(error.details);
        return;
      }
      notify({
        tone: "error",
        title: "Não foi possível remover o produto",
        description:
          error instanceof Error ? error.message : "Tente novamente.",
      });
    }
  };

  const handleResolution = async (selected: ResolutionAction) => {
    if (!conflict) {
      return;
    }
    setAction(selected);
    const shouldPause = selected === "pause" || selected === "pause-unbind";
    const shouldUnbind = selected === "unbind" || selected === "pause-unbind";
    try {
      if (shouldPause) {
        await pauseAndZero.mutateAsync(conflict.listings);
      }
      if (shouldUnbind) {
        await unbindListings.mutateAsync(product.productId);
      }
      await finishDeletion();
    } catch (error) {
      if (isDeletionConflict(error)) {
        setConflict(error.details);
        notify({
          tone: "info",
          title: "Ainda há anúncios ativos",
          description:
            "Novos anúncios ativos apareceram. Resolva-os para concluir a exclusão.",
        });
        return;
      }
      const failedStep = shouldPause
        ? "pausar/zerar os anúncios"
        : "desvincular os anúncios";
      notify({
        tone: "error",
        title: `Não foi possível ${failedStep}`,
        description:
          "A exclusão foi abortada e o produto foi mantido. Tente novamente.",
      });
    } finally {
      setAction(null);
    }
  };

  if (!conflict) {
    return (
      <ConfirmDialog
        open
        title="Apagar produto"
        description={`"${product.title}" será arquivado junto com seu SKU. Se houver anúncios ativos, você poderá pausar, zerar ou desvincular antes de concluir.`}
        confirmLabel={deleteProduct.isPending ? "Apagando..." : "Apagar"}
        confirmDisabled={busy}
        onCancel={onClose}
        onConfirm={handleInitialDelete}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/40"
        onClick={() => {
          if (!busy) {
            onClose();
          }
        }}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-deletion-title"
        className="relative w-full max-w-lg rounded-card border border-line bg-surface p-5 shadow-pop"
      >
        <div className="flex items-start gap-3">
          <span className="rounded-full bg-amber-100 p-2 text-amber-700">
            <AlertTriangle aria-hidden="true" className="h-5 w-5" />
          </span>
          <div>
            <h2
              id="product-deletion-title"
              className="text-base font-semibold text-slate-900"
            >
              Anúncios ativos vinculados
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              O produto "{conflict.product_name}" não pode ser excluído enquanto
              houver anúncios ativos. Escolha como resolvê-los.
            </p>
          </div>
        </div>

        <ul className="mt-4 space-y-2">
          {conflict.listings.map((listing) => (
            <li
              key={listing.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-slate-50/60 px-3 py-2 text-sm"
            >
              <div className="min-w-0">
                <p className="font-mono text-xs font-semibold text-slate-800">
                  {listing.id}
                </p>
                <p className="text-xs text-slate-500">
                  {statusLabel(listing.status)}
                </p>
              </div>
              {listing.permalink ? (
                <a
                  href={listing.permalink}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline"
                >
                  Abrir anúncio no ML
                  <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                </a>
              ) : null}
            </li>
          ))}
        </ul>

        <div className="mt-5 space-y-2">
          <Button
            className="w-full justify-center"
            onClick={() => handleResolution("pause")}
            disabled={busy}
          >
            {action === "pause" ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <PauseCircle aria-hidden="true" className="h-4 w-4" />
            )}
            Pausar e zerar
          </Button>
          <Button
            variant="secondary"
            className="w-full justify-center"
            onClick={() => handleResolution("unbind")}
            disabled={busy}
          >
            {action === "unbind" ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Unlink aria-hidden="true" className="h-4 w-4" />
            )}
            Desvincular
          </Button>
          <Button
            variant="danger"
            className="w-full justify-center"
            onClick={() => handleResolution("pause-unbind")}
            disabled={busy}
          >
            {action === "pause-unbind" ? (
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 aria-hidden="true" className="h-4 w-4" />
            )}
            Pausar, zerar e desvincular
          </Button>
          <Button
            variant="ghost"
            className="w-full justify-center"
            onClick={onClose}
            disabled={busy}
          >
            Cancelar
          </Button>
        </div>
      </div>
    </div>
  );
}
