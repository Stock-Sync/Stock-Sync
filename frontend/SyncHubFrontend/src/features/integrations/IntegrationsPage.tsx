import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, AlertCircle, ExternalLink, Trash2, Loader2, CheckCircle } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { PageHeader } from "../../components/ui/PageHeader";
import { EmptyState } from "../../components/ui/EmptyState";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/toast-context";
import { integrationsClient, type CredentialResponse } from "../../lib/api/integrations-client";

interface Credential extends CredentialResponse {
  statusLabel: string;
  statusTone: "success" | "warning" | "neutral" | "danger";
}

export function IntegrationsPage() {
  const { notify } = useToast();
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadCredentials = async () => {
    try {
      const creds = await integrationsClient.listMercadoLivreCredentials();
      setCredentials(
        creds.map((c) => ({
          ...c,
          statusLabel: c.is_active ? "Conectado" : "Desconectado",
          statusTone: c.is_active ? "success" : "warning",
        }))
      );
    } catch (error) {
      console.error("Failed to load credentials:", error);
      notify({ tone: "error", title: "Erro ao carregar integrações" });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCredentials();
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const { auth_url } = await integrationsClient.getMercadoLivreAuthUrl();
      // Redirect to Mercado Livre OAuth
      window.location.href = auth_url;
    } catch (error) {
      notify({ tone: "error", title: "Erro ao iniciar conexão" });
      setConnecting(false);
    }
  };

  const handleDisconnect = (credential: Credential) => {
    setDeletingId(credential.id);
  };

  const confirmDisconnect = async () => {
    if (!deletingId) return;
    try {
      await integrationsClient.deleteMercadoLivreCredential(deletingId);
      notify({ tone: "success", title: "Conta desconectada" });
      loadCredentials();
    } catch (error) {
      notify({ tone: "error", title: "Erro ao desconectar" });
    } finally {
      setDeletingId(null);
    }
  };

  const cancelDisconnect = () => setDeletingId(null);

  const getProfileUrl = (nickname: string | null) => {
    if (!nickname) return null;
    return `https://perfil.mercadolivre.com.br/${nickname}`;
  };

  const renderProfileLink = (nickname: string | null) => {
    const url = getProfileUrl(nickname);
    if (!url) return null;
    return (
      <Link
        to={url}
        target="_blank"
        rel="noopener noreferrer"
        title="Ver perfil no Mercado Livre"
        className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
        aria-label={`Ver perfil no Mercado Livre`}
      >
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
      </Link>
    );
  };

  const formatExpiresAt = (dateStr: string | null) => {
    if (!dateStr) return "Não expira";
    const date = new Date(dateStr);
    const now = new Date();
    if (date < now) return "Expirado";
    const diffHours = Math.floor((date.getTime() - now.getTime()) / (1000 * 60 * 60));
    if (diffHours < 24) return `Expira em ${diffHours}h`;
    const diffDays = Math.floor(diffHours / 24);
    return `Expira em ${diffDays}d`;
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrações"
        description="Gerencie suas conexões com marketplaces para sincronizar produtos e pedidos."
        actions={
          <Button onClick={handleConnect} disabled={connecting || isLoading} className="gap-2">
            <Plus aria-hidden="true" className="h-4 w-4" />
            {connecting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Conectando...
              </>
            ) : (
              "Conectar Mercado Livre"
            )}
          </Button>
        }
      />

      <Card>
        <CardHeader
          title="Mercado Livre"
          description="Contas conectadas para publicação de anúncios e recebimento de pedidos."
        />
        <CardBody className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-brand-700" />
            </div>
          ) : credentials.length === 0 ? (
            <EmptyState
              icon={<ExternalLink aria-hidden="true" className="h-8 w-8" />}
              title="Nenhuma conta conectada"
              description="Conecte sua conta do Mercado Livre para começar a publicar produtos e receber pedidos automaticamente."
              action={
                <Button onClick={handleConnect} disabled={connecting} className="gap-2">
                  <Plus aria-hidden="true" className="h-4 w-4" />
                  Conectar Mercado Livre
                </Button>
              }
            />
          ) : (
            <div className="divide-y divide-line">
              {credentials.map((credential) => (
                <div key={credential.id} className="flex flex-col md:flex-row md:items-center md:justify-between p-4 gap-4">
                  <div className="flex items-center gap-4">
                    <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-yellow-100">
                      <ExternalLink aria-hidden="true" className="h-6 w-6 text-yellow-700" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-900">{credential.account_name}</h3>
                      <p className="text-sm text-slate-500">
                        ID do vendedor: {credential.ml_user_id ?? "—"}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row md:items-center gap-3 w-full md:w-auto">
                    <Badge tone={credential.statusTone}>
                      <CheckCircle className="h-3 w-3 mr-1" aria-hidden="true" />
                      {credential.statusLabel}
                    </Badge>

                    <span className="text-xs text-slate-500 hidden md:inline-flex items-center gap-1">
                      {credential.expires_at && (
                        <>
                          <AlertCircle className="h-3 w-3" aria-hidden="true" />
                          {formatExpiresAt(credential.expires_at)}
                        </>
                      )}
                    </span>

                    <div className="flex items-center gap-2">
                      {renderProfileLink(credential.ml_nickname)}

                      <button
                        type="button"
                        onClick={() => handleDisconnect(credential)}
                        disabled={deletingId === credential.id}
                        aria-label={`Desconectar ${credential.account_name}`}
                        className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-50"
                      >
                        <Trash2 aria-hidden="true" className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {credentials.length > 0 && (
        <Card>
          <CardHeader title="Outros Marketplaces" />
          <CardBody>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div className="flex items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-300 p-6 bg-slate-50">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-brand-100">
                  <span className="text-xs font-bold text-brand-700">SP</span>
                </div>
                <div>
                  <h4 className="font-medium text-slate-700">Shopee</h4>
                  <p className="text-sm text-slate-500">Integração em desenvolvimento</p>
                </div>
              </div>
              <div className="flex items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-300 p-6 bg-slate-50">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-orange-100">
                  <span className="text-xs font-bold text-orange-700">AM</span>
                </div>
                <div>
                  <h4 className="font-medium text-slate-700">Amazon</h4>
                  <p className="text-sm text-slate-500">Integração planejada</p>
                </div>
              </div>
              <div className="flex items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-300 p-6 bg-slate-50">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-purple-100">
                  <span className="text-xs font-bold text-purple-700">MG</span>
                </div>
                <div>
                  <h4 className="font-medium text-slate-700">Magalu</h4>
                  <p className="text-sm text-slate-500">Integração planejada</p>
                </div>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <ConfirmDialog
        open={deletingId !== null}
        title="Desconectar conta"
        description="Esta ação removerá a conexão com o Mercado Livre. Os anúncios publicados permanecerão ativos no marketplace, mas não poderão mais ser sincronizados."
        confirmLabel="Desconectar"
        cancelLabel="Cancelar"
        onCancel={cancelDisconnect}
        onConfirm={confirmDisconnect}
      />
    </div>
  );
}