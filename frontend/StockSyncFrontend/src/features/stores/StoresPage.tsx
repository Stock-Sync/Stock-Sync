import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { PageHeader } from "../../components/ui/PageHeader";
import { paths } from "../../routes/paths";
import { StoresTable } from "./StoresTable";

/**
 * Página de lojas (destino da sidebar "Lojas").
 *
 * Mesma listagem da seção "Minhas Lojas" do perfil, porém em contexto de
 * página cheia — com as ações de criar loja no cabeçalho.
 */
export function StoresPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Lojas"
        description="Integrações com marketplaces conectados à sua conta."
        actions={
          <Link
            to={paths.storeNew}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
          >
            <Plus aria-hidden="true" className="h-4 w-4" />
            Adicionar Loja
          </Link>
        }
      />

      <Card>
        <CardHeader
          title="Marketplaces"
          description="Lojas disponíveis para publicação de anúncios."
        />
        <CardBody className="p-0">
          <StoresTable />
        </CardBody>
      </Card>

      <p className="text-center text-xs text-slate-400">
        Removendo uma loja aqui também a desvincula dos anúncios publicados.
      </p>
    </div>
  );
}