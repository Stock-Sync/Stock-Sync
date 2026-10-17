import { Package } from "lucide-react";
import { Card, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
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
  shipped: "brand",
  delivered: "neutral",
  cancelled: "danger",
};

const statusLabels: Record<string, string> = {
  paid: "Pago",
  shipped: "Enviado",
  delivered: "Entregue",
  cancelled: "Cancelado",
};

function statusLabel(status: string): string {
  return statusLabels[status] ?? status;
}

const columns: Column<Order>[] = [
  {
    key: "id",
    header: "Pedido",
    render: (row) => (
      <span className="font-mono text-xs font-semibold text-slate-800">
        {row.marketplace_order_id}
      </span>
    ),
  },
  {
    key: "marketplace",
    header: "Marketplace",
    render: (row) => row.marketplace,
  },
  {
    key: "sku",
    header: "SKU",
    render: (row) => (
      <span className="font-mono text-xs text-slate-600">{row.internal_sku}</span>
    ),
  },
  {
    key: "quantity",
    header: "Qtd.",
    align: "right",
    render: (row) => row.quantity,
  },
  {
    key: "total",
    header: "Total",
    align: "right",
    render: (row) => formatCurrency(row.total_amount),
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
    header: "Data",
    render: (row) => (
      <span className="text-slate-500">{formatDateTime(row.ordered_at)}</span>
    ),
  },
];

/**
 * Pedidos (destino da ação rápida "Ver Pedidos").
 *
 * Ainda é somente leitura: os dados vêm do mock do `sales-service` e não há
 * mutação implementada.
 */
export function OrdersPage() {
  const { data: orders = [], isPending } = useOrders();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Pedidos"
        description="Vendas recebidas dos marketplaces conectados."
      />

      <Card>
        <CardHeader title="Pedidos" />

        {isPending ? (
          <LoadingBlock label="Carregando pedidos..." />
        ) : orders.length === 0 ? (
          <EmptyState
            icon={<Package aria-hidden="true" className="h-5 w-5" />}
            title="Nenhum pedido encontrado."
            description="Conecte um marketplace para acompanhar suas vendas."
          />
        ) : (
          <Table
            columns={columns}
            rows={orders}
            rowKey={(row) => row.id}
            caption="Pedidos recebidos"
          />
        )}
      </Card>
    </div>
  );
}