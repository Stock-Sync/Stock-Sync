import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Megaphone, Pencil, Trash2, Plus } from "lucide-react";
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
import type { ListingView } from "../../types/catalog";
import {
  useDeletePlatformMapping,
  usePlatformMappings,
} from "./queries";
import {
  useProductViews,
} from "../products/queries";
import { useRunSync } from "../dashboard/queries";
import { paths } from "../../routes/paths";

/**
 * Anúncios (destino da sidebar "Anúncios").
 *
 * Exibe os vínculos locais produto ↔ marketplace (foco: Mercado Livre v3),
 * com sincronização, edição e exclusão. A criação agora é feita por meio da
 * página dedicada /listings/new (assistente multi-etapa), substituindo o
 * modal anterior.
 */
export function ListingsPage() {
  const { data: mappings = [], isPending } = usePlatformMappings();
  const { products } = useProductViews();
  const deleteListingMutation = useDeletePlatformMapping();
  const runSync = useRunSync();
  const { notify } = useToast();
  const navigate = useNavigate();

  const [pendingDeletion, setPendingDeletion] = useState<ListingView | null>(
    null
  );
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const rows: ListingView[] = useMemo(() => {
    const productBySku = new Map(products.map((item) => [item.skuId, item]));
    return mappings.map((mapping) => {
      const product = productBySku.get(mapping.sku_id);
      return {
        ...mapping,
        sku: product?.sku ?? `SKU #${mapping.sku_id}`,
        productTitle: product?.title ?? "Produto removido",
      };
    });
  }, [mappings, products]);

  const columns: Column<ListingView>[] = [
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
          {row.platform_sku ?? row.platform_product_id ?? "—"}
        </span>
      ),
    },
    {
      key: "product",
      header: "Produto",
      render: (row) => (
        <div className="min-w-0">
          <span className="font-mono text-xs text-slate-500">
            {row.sku}
          </span>
          <div className="text-slate-600">{row.productTitle}</div>
        </div>
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
        <span className="text-slate-500">
          {formatDateTime(row.updated_at)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Ações",
      align: "right",
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          <Link
            to={{
              pathname: paths.listingNew,
              search: `?listingId=${row.id}`,
            }}
            aria-label={`Editar anúncio ${row.platform_sku ?? row.id}`}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-700"
          >
            <Pencil aria-hidden="true" className="h-4 w-4" />
          </Link>
          <button
            type="button"
            onClick={() => {
              setPendingDeletion(row);
              setIsConfirmingDelete(true);
            }}
            aria-label={`Excluir anúncio ${row.platform_sku ?? row.id}`}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
          >
            <Trash2 aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
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

  const handleDelete = async () => {
    if (!pendingDeletion) {
      return;
    }
    try {
      await deleteListingMutation.mutateAsync(pendingDeletion.id);
      notify({ tone: "success", title: "Anúncio excluído" });
    } catch {
      notify({ tone: "error", title: "Não foi possível excluir o anúncio" });
    } finally {
      setIsConfirmingDelete(false);
      setPendingDeletion(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Anúncios"
        description="Produtos publicados nos marketplaces conectados."
        actions={
          <div className="flex items-center gap-2">
            <Button
              onClick={handleSyncAll}
              disabled={runSync.isPending}
            >
              {runSync.isPending ? "Sincronizando..." : "Sincronizar Tudo"}
            </Button>
            <Button
              onClick={() => navigate(paths.listingNew)}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              <Plus aria-hidden="true" className="h-4 w-4 mr-2" />
              Novo Anúncio
            </Button>
          </div>
        }
      />

      <Card>
        <CardHeader title="Anúncios publicados" />

        {isPending ? (
          <LoadingBlock label="Carregando anúncios..." />
        ) : rows.length === 0 ? (
          <>
            <EmptyState
              icon={<Megaphone aria-hidden="true" className="h-5 w-5" />}
              title="Nenhum anúncio vinculado."
              description="Crie um anúncio para publicar um produto do catálogo no Mercado Livre."
              action={
                <Button size="sm" onClick={handleSyncAll} disabled={runSync.isPending}>
                  Sincronizar Tudo
                </Button>
              }
            />
          </>
        ) : (
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            caption="Vínculos produto ↔ marketplace"
          />
        )}
      </Card>

      <ConfirmDialog
        open={isConfirmingDelete}
        title="Excluir anúncio"
        description={
          pendingDeletion
            ? `"${pendingDeletion.platform_sku}" deixará de estar publicado. O produto continua no catálogo interno.`
            : ""
        }
        confirmLabel="Excluir"
        onCancel={() => setIsConfirmingDelete(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
