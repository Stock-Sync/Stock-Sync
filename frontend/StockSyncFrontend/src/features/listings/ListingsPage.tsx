import { useMemo, useState } from "react";
import { Megaphone, RefreshCw, Trash2 } from "lucide-react";
import { Card, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { LoadingBlock } from "../../components/ui/Spinner";
import { PageHeader } from "../../components/ui/PageHeader";
import { Table } from "../../components/ui/Table";
import type { Column } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { formatDateTime } from "../../lib/format";
import { platformLabel } from "../../types/catalog";
import type { PlatformMapping } from "../../types/catalog";
import {
  useAllListings,
  useDeleteListing,
  useProductViews,
} from "../products/queries";
import { useRunSync } from "../dashboard/queries";

interface ListingRow extends PlatformMapping {
  skuLabel: string;
  productTitle: string;
}

/**
 * Anúncios (destino da sidebar "Anúncios").
 *
 * Funcional sobre os `PlatformMapping` mockados: sincroniza tudo e permite
 * desvincular anúncios individuais.
 */
export function ListingsPage() {
  const { data: listings = [], isPending } = useAllListings();
  const { products } = useProductViews();
  const deleteListing = useDeleteListing();
  const runSync = useRunSync();
  const { notify } = useToast();
  const [pendingDeletion, setPendingDeletion] = useState<ListingRow | null>(
    null
  );

  const rows = useMemo<ListingRow[]>(() => {
    const productBySku = new Map(products.map((item) => [item.skuId, item]));
    return listings.map((listing) => {
      const product = productBySku.get(listing.sku_id);
      return {
        ...listing,
        skuLabel: product?.sku ?? `SKU #${listing.sku_id}`,
        productTitle: product?.title ?? "Produto removido",
      };
    });
  }, [listings, products]);

  const columns: Column<ListingRow>[] = [
    {
      key: "platform",
      header: "Marketplace",
      render: (row) => (
        <span className="font-medium text-slate-800">
          {platformLabel(row.platform)}
        </span>
      ),
    },
    {
      key: "platformSku",
      header: "SKU no marketplace",
      render: (row) => (
        <span className="font-mono text-xs text-slate-600">
          {row.platform_sku}
        </span>
      ),
    },
    {
      key: "product",
      header: "Produto",
      render: (row) => (
        <span className="text-slate-600">{row.productTitle}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      align: "center",
      render: (row) => (
        <Badge tone={row.is_active ? "success" : "neutral"}>
          {row.is_active ? "Ativo" : "Inativo"}
        </Badge>
      ),
    },
    {
      key: "updated",
      header: "Atualizado",
      render: (row) => (
        <span className="text-slate-500">{formatDateTime(row.updated_at)}</span>
      ),
    },
    {
      key: "actions",
      header: "Ações",
      align: "right",
      render: (row) => (
        <button
          type="button"
          onClick={() => setPendingDeletion(row)}
          aria-label={`Desvincular anúncio ${row.platform_sku}`}
          className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
        >
          <Trash2 aria-hidden="true" className="h-4 w-4" />
        </button>
      ),
    },
  ];

  const handleSyncAll = async () => {
    try {
      const created = await runSync.mutateAsync();
      notify({
        tone: "success",
        title: "Sincronização concluída",
        description:
          created > 0
            ? `${created} anúncio(s) publicado(s).`
            : "Nada novo para publicar.",
      });
    } catch {
      notify({ tone: "error", title: "Falha na sincronização" });
    }
  };

  const confirmDelete = async () => {
    if (!pendingDeletion) {
      return;
    }
    try {
      await deleteListing.mutateAsync(pendingDeletion.id);
      notify({ tone: "success", title: "Anúncio desvinculado" });
    } catch {
      notify({ tone: "error", title: "Não foi possível desvincular" });
    } finally {
      setPendingDeletion(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Anúncios"
        description="Produtos publicados nos marketplaces conectados."
        actions={
          <Button onClick={handleSyncAll} disabled={runSync.isPending}>
            <RefreshCw
              aria-hidden="true"
              className={
                runSync.isPending ? "h-4 w-4 animate-spin" : "h-4 w-4"
              }
            />
            {runSync.isPending ? "Sincronizando..." : "Sincronizar Tudo"}
          </Button>
        }
      />

      <Card>
        <CardHeader title="Anúncios ativos" />

        {isPending ? (
          <LoadingBlock label="Carregando anúncios..." />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Megaphone aria-hidden="true" className="h-5 w-5" />}
            title="Nenhum anúncio vinculado."
            description="Sincronize seus produtos para publicá-los nos marketplaces."
            action={
              <Button size="sm" onClick={handleSyncAll} disabled={runSync.isPending}>
                Sincronizar Tudo
              </Button>
            }
          />
        ) : (
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            caption="Anúncios publicados"
          />
        )}
      </Card>

      <ConfirmDialog
        open={pendingDeletion !== null}
        title="Desvincular anúncio"
        description={
          pendingDeletion
            ? `"${pendingDeletion.platform_sku}" deixará de estar publicado. O produto continua no catálogo.`
            : ""
        }
        confirmLabel="Desvincular"
        onCancel={() => setPendingDeletion(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}