import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil } from "lucide-react";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Avatar } from "../../components/ui/Avatar";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { formatCurrency, formatDateTime } from "../../lib/format";
import { paths } from "../../routes/paths";
import { useProductView } from "./queries";

/**
 * Detalhe do produto (Imagem 4).
 *
 * Card de resumo com avatar da inicial, título, descrição, preço e botão
 * "Editar". Escopo estritamente interno: dados de marketplace (anúncios,
 * categorias, atributos) vivem em /listings, não aqui.
 */
export function ProductDetailPage() {
  const { id } = useParams();
  const productId = Number(id);
  const navigate = useNavigate();

  const { product, isPending } = useProductView(productId);

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
    </div>
  );
}