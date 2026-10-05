import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Megaphone, Pencil } from "lucide-react";
import { Card, CardBody, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Avatar } from "../../components/ui/Avatar";
import { Badge } from "../../components/ui/Badge";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { useToast } from "../../components/ui/toast-context";
import { PLATFORM_LABELS } from "../../types/catalog";
import { formatCurrency, formatDateTime } from "../../lib/format";
import { paths } from "../../routes/paths";
import {
  useCreateListingForSku,
  useListingsForSku,
  useProductView,
} from "./queries";

/**
 * Detalhe do produto (Imagem 4).
 *
 * Card de resumo com avatar da inicial, título, descrição, preço e botão
 * "Editar"; abaixo, a seção de anúncios vinculados.
 */
export function ProductDetailPage() {
  const { id } = useParams();
  const productId = Number(id);
  const navigate = useNavigate();
  const { notify } = useToast();
  const { product, isPending } = useProductView(productId);
  const listings = useListingsForSku(product?.skuId);
  const createListing = useCreateListingForSku();

  if (isPending) {
    return <LoadingBlock label="Carregando produto..." />;
  }

  if (!product) {
    return (
      <EmptyState
        title="Produto não encontrado"
        description="O produto pode ter sido removido."
        action={
          <Link
            to={paths.products}
            className="text-sm font-semibold text-brand-700 hover:underline"
          >
            Voltar para produtos
          </Link>
        }
      />
    );
  }

  const handleSync = async () => {
    try {
      await createListing.mutateAsync(product.skuId);
      notify({
        tone: "success",
        title: "Anúncio sincronizado",
        description: product.title,
      });
    } catch {
      notify({ tone: "error", title: "Falha ao sincronizar anúncio" });
    }
  };

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(paths.products)}
        className="-ml-2"
      >
        <ArrowLeft aria-hidden="true" className="h-4 w-4" />
        Produtos
      </Button>

      <Card>
        <CardBody className="flex flex-wrap items-start justify-between gap-6 p-6">
          <div className="flex min-w-0 items-start gap-4">
            <Avatar label={product.title} size="lg" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-slate-900">
                {product.title}{" "}
                <span className="font-mono text-sm font-normal text-slate-500">
                  ({product.sku})
                </span>
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                {product.description || "Sem descrição."}
              </p>
              <p className="mt-3 text-2xl font-extrabold text-slate-900">
                {formatCurrency(product.price)}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Atualizado em {formatDateTime(product.updatedAt)}
              </p>
            </div>
          </div>

          <Link
            to={paths.productEdit(product.id)}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
          >
            <Pencil aria-hidden="true" className="h-4 w-4" />
            Editar
          </Link>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Anúncios vinculados"
          description="Produtos publicados nos marketplaces conectados."
          action={
            <Button
              size="sm"
              onClick={handleSync}
              disabled={createListing.isPending}
            >
              {createListing.isPending ? "Sincronizando..." : "Anunciar agora"}
            </Button>
          }
        />

        {listings.isPending ? (
          <LoadingBlock label="Carregando anúncios..." />
        ) : listings.data && listings.data.length > 0 ? (
          <ul className="divide-y divide-line">
            {listings.data.map((listing) => (
              <li
                key={listing.id}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                    <Megaphone aria-hidden="true" className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-slate-800">
                      {PLATFORM_LABELS[listing.platform]}
                    </p>
                    <p className="font-mono text-xs text-slate-500">
                      {listing.platform_sku}
                    </p>
                  </div>
                </div>
                <Badge tone={listing.is_active ? "success" : "neutral"}>
                  {listing.is_active ? "Ativo" : "Inativo"}
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Megaphone aria-hidden="true" className="h-5 w-5" />}
            title="Nenhum anúncio vinculado."
            description="Sincronize o produto para publicá-lo nos marketplaces."
          />
        )}
      </Card>
    </div>
  );
}