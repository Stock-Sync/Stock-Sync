import { useState } from "react";
import { ShoppingBag } from "lucide-react";
import { Card, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { PageHeader } from "../../components/ui/PageHeader";
import { Table } from "../../components/ui/Table";
import type { Column } from "../../components/ui/Table";
import type { BadgeTone } from "../../components/ui/Badge";
import { formatCurrency, formatDateTime } from "../../lib/format";
import type { Order } from "../../types/entities";
import { useOrders } from "./queries";

const statusTones: Record<string, BadgeTone> = {
  paid: "success",
  confirmed: "success",
  shipped: "brand",
  delivered: "neutral",
  cancelled: "danger",
};

const statusLabels: Record<string, string> = {
  paid: "Pago",
  confirmed: "Confirmado",
  shipped: "Enviado",
  delivered: "Entregue",
  cancelled: "Cancelado",
};

function statusLabel(status: string): string {
  return statusLabels[status] ?? status;
}

const PAGE_SIZE = 20;

function ProductCell({ order }: { order: Order }) {
  return (
    <div className="flex items-center gap-3">
      {order.thumbnail_url ? (
        <img
          src={order.thumbnail_url}
          alt=""
          className="h-10 w-10 rounded-lg border border-slate-200 object-cover"
        />
      ) : (
        <span
          aria-hidden="true"
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100 text-slate-400"
        >
          <ShoppingBag className="h-4 w-4" />
        </span>
      )}
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-slate-800">
          {order.item_title ?? "Anúncio"}
        </p>
        <p className="font-mono text-xs text-slate-500">{order.marketplace_order_id}</p>
      </div>
    </div>
  );
}

const columns: Column<Order>[] = [
  {
    key: "product",
    header: "Produto",
    render: (row) => <ProductCell order={row} />,
  },
  {
    key: "sku",
    header: "SKU",
    render: (row) => (
      <span className="font-mono text-xs text-slate-600">
        {row.internal_sku ?? "—"}
      </span>
    ),
  },
  {
    key: "quantity",
    header: "Qtd. vendida",
    align: "right",
    render: (row) => row.quantity,
  },
  {
    key: "unit",
    header: "Preço unit.",
    align: "right",
    render: (row) => formatCurrency(row.unit_price),
  },
  {
    key: "total",
    header: "Total",
    align: "right",
    render: (row) => (
      <span className="font-semibold text-slate-800">
        {formatCurrency(row.total_amount)}
      </span>
    ),
  },
  {
    key: "buyer",
    header: "Comprador",
    render: (row) => (
      <span className="text-sm text-slate-600">
        {row.buyer_nickname ?? "—"}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    align: "center",
    render: (row) => (
      <Badge tone={statusTones[row.status] ?? "neutral"}>
        {statusLabel(row.status)}
      </Badge>
    ),
  },
  {
    key: "orderedAt",
    header: "Data da compra",
    render: (row) => (
      <span className="text-slate-500">{formatDateTime(row.ordered_at)}</span>
    ),
  },
];

/**
 * Vendas (histórico).
 *
 * Alimenta-se do sales-service (GET /api/v1/orders), que é preenchido pelo
 * sync-service a partir dos webhooks do Mercado Livre processados via
 * Redis Streams.
 */
export function OrdersPage() {
  const [page, setPage] = useState(1);
  const { data, isPending } = useOrders({ page, limit: PAGE_SIZE });

  const orders = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Vendas"
        description="Histórico de vendas recebidas dos marketplaces conectados."
      />

      <Card>
        <CardHeader title="Histórico de vendas" />

        {isPending ? (
          <LoadingBlock label="Carregando vendas..." />
        ) : orders.length === 0 ? (
          <EmptyState
            icon={<ShoppingBag aria-hidden="true" className="h-5 w-5" />}
            title="Nenhuma venda encontrada."
            description="As vendas do Mercado Livre aparecem aqui automaticamente após a primeira compra."
          />
        ) : (
          <>
            <Table
              columns={columns}
              rows={orders}
              rowKey={(row) => row.id}
              caption="Vendas recebidas"
            />
            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
                <span className="text-xs text-slate-500">
                  Página {page} de {totalPages} · {total} venda(s)
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((current) => current - 1)}
                  >
                    Anterior
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((current) => current + 1)}
                  >
                    Próxima
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
