import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Megaphone, Pause, Pencil, Trash2, Plus } from "lucide-react";
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
import type { Platform, PlatformMapping } from "../../types/catalog";
import {
  useDeletePlatformMapping,
  useLocalMarketplaceItems,
  usePauseMlListings,
  usePlatformMappings,
} from "./queries";
import { useProductViews } from "../products/queries";
import { useRunSync } from "../dashboard/queries";
import { paths } from "../../routes/paths";

/**
 * Linha unificada da tela de anúncios.
 *
 * Combina o anúncio importado (`MarketplaceItem`) com o vínculo local
 * (`PlatformMapping`). Um item importado sem vínculo — ou cujo produto/SKU foi
 * arquivado — aparece com o badge de aviso e pode ser pausado no marketplace.
 */
interface ListingRow {
  key: string;
  mapping: PlatformMapping | null;
  itemId: string | null;
  platform: Platform;
  platformSku: string;
  title: string;
  sku: string;
  productTitle: string;
  isActive: boolean;
  isLinked: boolean;
  updatedAt: string;
}

/**
 * Anúncios (destino da sidebar "Anúncios").
 *
 * Exibe os vínculos locais produto ↔ marketplace e os anúncios importados do
 * Mercado Livre, com sincronização, edição, pausa e exclusão do vínculo. A
 * criação continua na página dedicada /listings/new (assistente multi-etapa).
 */
export function ListingsPage() {
  const { data: mappings = [], isPending: mappingsPending } =
    usePlatformMappings();
  const { data: localItems = [], isPending: itemsPending } =
    useLocalMarketplaceItems();
  const { products } = useProductViews();
  const deleteListingMutation = useDeletePlatformMapping();
  const pauseListings = usePauseMlListings();
  const runSync = useRunSync();
  const { notify } = useToast();
  const navigate = useNavigate();

  const [pendingDeletion, setPendingDeletion] = useState<ListingRow | null>(
    null
  );
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

  const rows: ListingRow[] = useMemo(() => {
    const productBySku = new Map(products.map((item) => [item.skuId, item]));
    const mappingByItemId = new Map<string, PlatformMapping>();
    for (const mapping of mappings) {
      if (mapping.platform_product_id) {
        mappingByItemId.set(mapping.platform_product_id, mapping);
      }
    }

    const result: ListingRow[] = [];
    const usedMappings = new Set<number>();

    for (const item of localItems) {
      const mapping = mappingByItemId.get(item.item_id) ?? null;
      if (mapping) {
        usedMappings.add(mapping.id);
      }
      const product =
        mapping?.sku_id != null
          ? productBySku.get(mapping.sku_id)
          : item.sku_id != null
            ? productBySku.get(item.sku_id)
            : undefined;
      const isActive = mapping
        ? mapping.is_active
        : item.status === "active";

      result.push({
        key: `item-${item.item_id}`,
        mapping,
        itemId: item.item_id,
        platform: mapping?.platform ?? "mercado_livre",
        platformSku: mapping?.platform_sku ?? item.item_id,
        title: item.title,
        sku: product?.sku ?? (item.sku_id != null ? `SKU #${item.sku_id}` : "—"),
        productTitle: product?.title ?? "Produto arquivado ou não vinculado",
        isActive,
        isLinked: Boolean(mapping?.is_active && product),
        updatedAt: item.updated_at ?? mapping?.updated_at ?? new Date().toISOString(),
      });
    }

    // Mappings sem item local correspondente (ex.: importação ainda pendente).
    for (const mapping of mappings) {
      if (usedMappings.has(mapping.id)) {
        continue;
      }
      const product = productBySku.get(mapping.sku_id);
      result.push({
        key: `mapping-${mapping.id}`,
        mapping,
        itemId: mapping.platform_product_id,
        platform: mapping.platform,
        platformSku: mapping.platform_sku,
        title: product?.title ?? mapping.platform_sku,
        sku: product?.sku ?? `SKU #${mapping.sku_id}`,
        productTitle: product?.title ?? "Produto arquivado ou não vinculado",
        isActive: mapping.is_active,
        isLinked: Boolean(mapping.is_active && product),
        updatedAt: mapping.updated_at,
      });
    }

    return result;
  }, [localItems, mappings, products]);

  const columns: Column<ListingRow>[] = [
    {
      key: "platform",
      header: "Marketplace",
      render: (row) => (
        <div className="min-w-0">
          <span className="font-medium text-slate-800">
            {platformLabel(row.platform)}
          </span>
          <div className="truncate text-xs text-slate-500">{row.title}</div>
        </div>
      ),
    },
    {
      key: "platformSku",
      header: "SKU no marketplace",
      render: (row) => (
        <span className="font-mono text-xs text-slate-600">
          {row.platformSku ?? row.itemId ?? "—"}
        </span>
      ),
    },
    {
      key: "product",
      header: "Produto",
      render: (row) => (
        <div className="min-w-0">
          <span className="font-mono text-xs text-slate-500">{row.sku}</span>
          <div className="text-slate-600">{row.productTitle}</div>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      align: "center",
      render: (row) => (
        <div className="flex flex-col items-center gap-1">
          <Badge tone={row.isActive ? "success" : "neutral"}>
            {row.isActive ? "Ativo" : "Inativo"}
          </Badge>
          {!row.isLinked && (
            <Badge tone="warning">Desvinculado / Produto arquivado</Badge>
          )}
        </div>
      ),
    },
    {
      key: "updated",
      header: "Atualizado",
      render: (row) => (
        <span className="text-slate-500">
          {formatDateTime(row.updatedAt)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Ações",
      align: "right",
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          {row.mapping && (
            <Link
              to={{
                pathname: paths.listingNew,
                search: `?listingId=${row.mapping.id}`,
              }}
              aria-label={`Vincular a outro produto ${row.platformSku ?? row.mapping.id}`}
              title="Vincular a outro produto / editar"
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-700"
            >
              <Pencil aria-hidden="true" className="h-4 w-4" />
            </Link>
          )}
          {row.platform === "mercado_livre" &&
            row.itemId &&
            row.isActive && (
              <button
                type="button"
                onClick={() => handlePause(row)}
                disabled={pauseListings.isPending}
                aria-label={`Pausar anúncio ${row.platformSku ?? row.itemId}`}
                title="Pausar no Mercado Livre"
                className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-amber-50 hover:text-amber-600 disabled:opacity-50"
              >
                <Pause aria-hidden="true" className="h-4 w-4" />
              </button>
            )}
          {row.mapping && (
            <button
              type="button"
              onClick={() => {
                setPendingDeletion(row);
                setIsConfirmingDelete(true);
              }}
              aria-label={`Excluir vínculo ${row.platformSku ?? row.mapping.id}`}
              title="Excluir vínculo local"
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
            >
              <Trash2 aria-hidden="true" className="h-4 w-4" />
            </button>
          )}
        </div>
      ),
    },
  ];

  const handleSyncAll = async () => {
    try {
      const result = await runSync.mutateAsync();
      notify({
        tone: "success",
        title: "Sincronização concluída",
        description: `${result.items_upserted} anúncio(s) sincronizado(s), ${result.mappings_created} vínculo(s) criado(s).`,
      });
    } catch {
      notify({ tone: "error", title: "Falha na sincronização" });
    }
  };

  const handlePause = async (row: ListingRow) => {
    if (row.platform !== "mercado_livre" || !row.itemId) {
      return;
    }
    try {
      await pauseListings.mutateAsync([
        {
          platform: "mercado_livre",
          "platform_product_id": row.itemId,
          "is_active": true,
        },
      ]);
      notify({
        tone: "success",
        title: "Anúncio pausado",
        description: row.title,
      });
    } catch {
      notify({
        tone: "error",
        title: "Não foi possível pausar o anúncio",
      });
    }
  };

  const handleDelete = async () => {
    if (!pendingDeletion?.mapping) {
      return;
    }
    try {
      await deleteListingMutation.mutateAsync(pendingDeletion.mapping.id);
      notify({ tone: "success", title: "Vínculo excluído" });
    } catch {
      notify({ tone: "error", title: "Não foi possível excluir o vínculo" });
    } finally {
      setIsConfirmingDelete(false);
      setPendingDeletion(null);
    }
  };

  const isPending = mappingsPending || itemsPending;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Anúncios"
        description="Produtos publicados nos marketplaces conectados."
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={handleSyncAll} disabled={runSync.isPending}>
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
                <Button
                  size="sm"
                  onClick={handleSyncAll}
                  disabled={runSync.isPending}
                >
                  Sincronizar Tudo
                </Button>
              }
            />
          </>
        ) : (
          <Table
            columns={columns}
            rows={rows}
            rowKey={(row) => row.key}
            caption="Vínculos produto ↔ marketplace"
          />
        )}
      </Card>

      <ConfirmDialog
        open={isConfirmingDelete}
        title="Excluir vínculo"
        description={
          pendingDeletion
            ? `"${pendingDeletion.platformSku}" deixará de estar vinculado. O anúncio continua publicado no marketplace; use "Pausar" se quiser encerrá-lo. O produto continua no catálogo interno.`
            : ""
        }
        confirmLabel="Excluir"
        onCancel={() => setIsConfirmingDelete(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}
