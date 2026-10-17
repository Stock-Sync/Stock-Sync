import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Avatar } from "../../components/ui/Avatar";
import { PageHeader } from "../../components/ui/PageHeader";
import { useAuth } from "../../auth/auth-context";
import { paths } from "../../routes/paths";
import { StoresTable } from "../stores/StoresTable";

/**
 * Perfil do usuário (Imagem 7).
 *
 * Mostra os dados da sessão e a seção "Minhas Lojas" com a ação "Adicionar
 * Loja", que leva ao formulário da Imagem 9.
 */
export function ProfilePage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <PageHeader title="Meu Perfil" />

      <Card>
        <CardBody className="flex items-center gap-4 p-6">
          <Avatar label={user?.username ?? ""} size="lg" />
          <div className="min-w-0">
            <p className="text-sm text-slate-500">
              Usuário:{" "}
              <span className="font-semibold text-slate-900">
                {user?.username}
              </span>
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Email: <span className="text-slate-700">{user?.email || "—"}</span>
            </p>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Minhas Lojas"
          description="Marketplaces vinculados ao seu usuário."
          action={
            <Link
              to={paths.storeNew}
              className="inline-flex h-9 items-center justify-center gap-2 rounded-xl bg-brand-700 px-3 text-xs font-semibold text-white transition-colors hover:bg-brand-800"
            >
              <Plus aria-hidden="true" className="h-4 w-4" />
              Adicionar Loja
            </Link>
          }
        />
        <CardBody className="p-0">
          <StoresTable />
        </CardBody>
      </Card>
    </div>
  );
}