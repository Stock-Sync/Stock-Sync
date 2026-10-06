import { Link } from "react-router-dom";
import { Store } from "lucide-react";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { Table } from "../../components/ui/Table";
import type { Column } from "../../components/ui/Table";
import { Badge } from "../../components/ui/Badge";
import { paths } from "../../routes/paths";
import type { Store as StoreType } from "../../types/entities";
import { useStores } from "./queries";

const columns: Column<StoreType>[] = [
  {
    key: "name",
    header: "Nome",
    render: (row) => (
      <span className="font-medium text-slate-800">{row.name}</span>
    ),
  },
  {
    key: "marketplace",
    header: "Marketplace",
    render: (row) => row.marketplace,
  },
  {
    key: "externalId",
    header: "External ID",
    render: (row) => (
      <span className="font-mono text-xs text-slate-600">
        {row.external_id}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    align: "right",
    render: () => <Badge tone="success">Conectada</Badge>,
  },
];

/**
 * Tabela "Minhas Lojas" (Imagem 7).
 *
 * Reutilizada na tela de perfil e na página de lojas — os dois pontos de
 * entrada compartilham a mesma listagem.
 */
export function StoresTable() {
  const { data: stores = [], isPending } = useStores();

  if (isPending) {
    return <LoadingBlock label="Carregando lojas..." />;
  }

  if (stores.length === 0) {
    return (
      <EmptyState
        icon={<Store aria-hidden="true" className="h-5 w-5" />}
        title="Você não possui lojas cadastradas."
        description="Conecte um marketplace para começar a publicar seus produtos."
        action={
          <Link
            to={paths.storeNew}
            className="text-sm font-semibold text-brand-700 hover:underline"
          >
            Adicionar Loja
          </Link>
        }
      />
    );
  }

  return (
    <Table
      columns={columns}
      rows={stores}
      rowKey={(row) => row.id}
      caption="Lojas cadastradas"
    />
  );
}

