import { Link, useNavigate } from "react-router-dom";
import { Bell, Megaphone, Package, Plus, Store } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { Button } from "../../components/ui/Button";
import { useAuth } from "../../auth/auth-context";
import { useToast } from "../../components/ui/toast-context";
import { paths } from "../../routes/paths";
import { formatDateTime } from "../../lib/format";
import {
  useMarkNotificationsAsRead,
  useNotifications,
  useRunSync,
} from "./queries";
import { useStores } from "../stores/queries";
import { useAllListings, useProductViews } from "../products/queries";

interface Metric {
  label: string;
  value: number;
  caption: string;
  icon: LucideIcon;
}

function MetricCard({ metric }: { metric: Metric }) {
  const Icon = metric.icon;
  return (
    <Card>
      <CardBody className="flex items-start justify-between gap-4 p-5">
        <div>
          <p className="text-sm font-medium text-slate-500">
            {metric.label}
          </p>
          <p className="mt-1 text-3xl font-extrabold text-slate-900">
            {metric.value}
          </p>
          <p className="mt-1 text-xs text-slate-400">{metric.caption}</p>
        </div>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
          <Icon aria-hidden="true" className="h-5 w-5" />
        </span>
      </CardBody>
    </Card>
  );
}

interface QuickAction {
  title: string;
  description: string;
  icon: LucideIcon;
  onClick: () => void;
  disabled?: boolean;
}

/**
 * Dashboard (Imagens 1 e 6).
 *
 * Mesmo layout para visitante e usuário autenticado; a diferença é a saudação
 * (`"Bem-vindo de volta, amoras!"` vs. sem nome) e a sessão no rodapé.
 */
export function DashboardPage() {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const { notify } = useToast();

  const { products } = useProductViews();
  const { data: stores = [] } = useStores();
  const { data: listings = [] } = useAllListings();
  const { data: notifications = [], isPending: notificationsPending } =
    useNotifications();
  const markAllAsRead = useMarkNotificationsAsRead();
  const runSync = useRunSync();

  const activeListings = listings.filter((listing) => listing.is_active).length;
  const unread = notifications.filter((item) => !item.is_read).length;

  const metrics: Metric[] = [
    {
      label: "Produtos",
      value: products.length,
      caption: "Total de SKUs.",
      icon: Package,
    },
    {
      label: "Lojas",
      value: stores.length,
      caption: "Marketplaces conectados.",
      icon: Store,
    },
    {
      label: "Anúncios",
      value: activeListings,
      caption: "Total de anúncios ativos.",
      icon: Megaphone,
    },
    {
      label: "Ações",
      value: unread,
      caption: "Notificações.",
      icon: Bell,
    },
  ];

  const quickActions: QuickAction[] = [
    {
      title: "Criar Produto",
      description: "Adicione um novo produto ao catálogo",
      icon: Plus,
      onClick: () => navigate(paths.productNew),
    },
    {
      title: "Sincronizar Tudo",
      description: "Atualize anúncios",
      icon: Megaphone,
      disabled: runSync.isPending,
      onClick: async () => {
        try {
          const created = await runSync.mutateAsync();
          notify({
            tone: "success",
            title: "Sincronização concluída",
            description:
              created > 0
                ? `${created} anúncio(s) publicado(s).`
                : "Todos os produtos já estão anunciados.",
          });
        } catch {
          notify({ tone: "error", title: "Falha na sincronização" });
        }
      },
    },
    {
      title: "Ver Pedidos",
      description: "Gerencie pedidos",
      icon: Package,
      onClick: () => navigate(paths.orders),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          {isAuthenticated && user
            ? `Bem-vindo de volta, ${user.username}!`
            : "Bem-vindo de volta!"}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Aqui está o resumo das suas vendas hoje
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {quickActions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.title}
              type="button"
              onClick={action.onClick}
              disabled={action.disabled}
              className="flex items-start gap-3 rounded-card border border-line bg-surface p-5 text-left shadow-card transition-colors hover:border-brand-300 disabled:opacity-60"
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
                <Icon aria-hidden="true" className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-slate-900">
                  {action.title}
                </span>
                <span className="mt-0.5 block text-xs text-slate-500">
                  {action.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <Card>
        <CardHeader
          title="Notificações"
          action={
            notifications.length > 0 ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => markAllAsRead.mutate()}
                disabled={markAllAsRead.isPending}
              >
                Marcar como lidas
              </Button>
            ) : null
          }
        />

        {notificationsPending ? (
          <LoadingBlock label="Carregando notificações..." />
        ) : notifications.length === 0 ? (
          <EmptyState
            icon={<Bell aria-hidden="true" className="h-5 w-5" />}
            title="Nenhuma notificação recente"
          />
        ) : (
          <ul className="divide-y divide-line">
            {notifications.map((notification) => (
              <li key={notification.id} className="px-5 py-4">
                <p className="text-sm font-semibold text-slate-800">
                  {notification.title}
                </p>
                <p className="mt-0.5 text-sm text-slate-500">
                  {notification.message}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {formatDateTime(notification.created_at)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {!isAuthenticated && (
        <p className="text-center text-sm text-slate-500">
          <Link
            to={paths.login}
            className="font-semibold text-brand-700 hover:underline"
          >
            Entre
          </Link>{" "}
          para sincronizar seus marketplaces.
        </p>
      )}
    </div>
  );
}