import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { AlertTriangle, Info } from "lucide-react";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Avatar } from "../../components/ui/Avatar";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { formatCurrency, formatDateTime } from "../../lib/format";
import { paths } from "../../routes/paths";
import { ProductDeleteDialog } from "./ProductDeleteDialog";
import { useProductView } from "./queries";

/**
 * Detalhe do produto (Imagem 4).
 *
 * Exibe o produto com avisos quando há anúncio ativo no Mercado Livre
 * (Plan 12): campos gerenciados pelo ML tornam-se somente leitura e banners
 * informativos são mostrados.
 */
export function ProductDetailPage() {
  const { id } = useParams();
  const productId = Number(id);
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);

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

  const showWarningBanner = product.hasActiveListing;

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

      {showWarningBanner && (
        <Card className="border-amber-200 bg-amber-50">
          <CardBody className="p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-amber-800">
                  Este produto tem anúncio ativo no Mercado Livre
                </p>
                <p className="text-xs text-amber-700 mt-1">
                  Título, descrição, fotos e preço são gerenciados via
                  Mercado Livre e não podem ser editados aqui.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {product.isDescriptionTruncated && (
        <Card className="border-blue-200 bg-blue-50">
          <CardBody className="p-4">
            <div className="flex items-start gap-3">
              <Info className="h-5 w-5 text-blue-600 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-blue-800">
                  Descrição truncada no resumo
                </p>
                <p className="text-xs text-blue-700 mt-1">
                  A descrição no Mercado Livre excede 2.000 caracteres e foi
                  truncada na visualização resumida.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardBody className="flex flex-wrap items-start justify-between gap-6 p-6">
          <div className="flex min-w-0 items-start gap-4">
            <Avatar label={product.title} size="lg" />
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-slate-900">
                {product.title}
                {showWarningBanner && (
                  <span className="ml-2 text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">
                    ML
                  </span>
                )}
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

          <div className="flex items-center gap-2">
            {!showWarningBanner && (
              <Link
                to={paths.productEdit(product.id)}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
              >
                <Pencil aria-hidden="true" className="h-4 w-4" />
                Editar
              </Link>
            )}
            {showWarningBanner && (
              <Button
                variant="outline"
                disabled
                className="h-10 items-center justify-center gap-2 rounded-lg bg-slate-100 px-4 text-sm font-medium text-slate-400 cursor-not-allowed"
                title="Campos gerenciados pelo ML são somente leitura"
              >
                <Pencil aria-hidden="true" className="h-4 w-4" />
                Editar (somente ML)
              </Button>
            )}
            <Button
              variant="ghost"
              className="text-red-600 hover:bg-red-50 hover:text-red-700"
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 aria-hidden="true" className="h-4 w-4" />
              Apagar
            </Button>
          </div>
        </CardBody>
      </Card>

      <ProductDeleteDialog
        key={deleteOpen ? product.productId : "closed"}
        product={deleteOpen ? product : null}
        onClose={() => setDeleteOpen(false)}
        onDeleted={() => {
          setDeleteOpen(false);
          navigate(paths.products);
        }}
      />
    </div>
  );
}
