import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LayoutGrid, Pencil, Rows3, Search, Trash2 } from "lucide-react";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Fab } from "../../components/ui/Fab";
import { Avatar } from "../../components/ui/Avatar";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/Spinner";
import { PageHeader } from "../../components/ui/PageHeader";
import { Table } from "../../components/ui/Table";
import type { Column } from "../../components/ui/Table";
import { useToast } from "../../components/ui/toast-context";
import { formatCurrency, formatDateTime } from "../../lib/format";
import { paths } from "../../routes/paths";
import { platformLabel } from "../../types/catalog";
import type { ProductView } from "../../types/view-models";
import { usePauseMlListings } from "../listings/queries";
import { useDeleteProduct, useProductListings, useProductViews } from "./queries";

type ViewMode = "table" | "grid";

/**
 * Lista de produtos (Imagem 5).
 *
 * Cabeçalho com busca por SKU/título, alternância tabela/grid e botão "Novo",
 * além do botão flutuante de criação no canto inferior direito.
 */
export function ProductsListPage() {
  const { products, isPending, error } = useProductViews();
  const deleteProduct = useDeleteProduct();
  const { notify } = useToast();
  const navigate = useNavigate();

  // `term` é o que está no campo; `appliedTerm` é o termo efetivamente filtrado.
  // O botão "Buscar" é o que promove um ao outro, como no mockup.
  const [term, setTerm] = useState("");
  const [appliedTerm, setAppliedTerm] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [pendingDeletion, setPendingDeletion] = useState<ProductView | null>(
    null
  );
  const [pauseOnDelete, setPauseOnDelete] = useState(true);
  const pauseListings = usePauseMlListings();
  const {
    data: pendingListings = [],
    isPending: listingsPending,
  } = useProductListings(pendingDeletion?.skuId);
  const pausableListings = useMemo(
    () =>
      pendingListings.filter(
        (listing) =>
          listing.platform === "mercado_livre" &&
          Boolean(listing.platform_product_id)
      ),
    [pendingListings]
  );

  const isDeleting = deleteProduct.isPending || pauseListings.isPending;

  const deletionDescription = useMemo(() => {
    if (!pendingDeletion) {
      return "";
    }
    if (listingsPending) {
      return `Verificando anúncios vinculados a "${pendingDeletion.title}"...`;
    }
    if (pendingListings.length === 0) {
      return `"${pendingDeletion.title}" será arquivado junto com seu SKU.`;
    }
    const listings = pendingListings
      .map(
        (listing) =>
          `${platformLabel(listing.platform)} (${listing.platform_sku})`
      )
      .join(", ");
    const listingAction =
      pauseOnDelete && pausableListings.length > 0
        ? "serão pausados no Mercado Livre"
        : "serão desativados apenas no catálogo local";
    return `"${pendingDeletion.title}" será arquivado, seu SKU será desativado e ${pendingListings.length} anúncio(s) ativo(s) ${listingAction}: ${listings}.`;
  }, [
    pendingDeletion,
    pendingListings,
    pausableListings,
    listingsPending,
    pauseOnDelete,
  ]);

  const filtered = useMemo(() => {
    const needle = appliedTerm.trim().toLowerCase();
    if (needle.length === 0) {
      return products;
    }
    return products.filter(
      (product) =>
        product.sku.toLowerCase().includes(needle) ||
        product.title.toLowerCase().includes(needle)
    );
  }, [products, appliedTerm]);

  const cancelDelete = () => {
    setPendingDeletion(null);
    setPauseOnDelete(true);
  };

  const confirmDelete = async () => {
    if (!pendingDeletion) {
      return;
    }

    if (pauseOnDelete && pausableListings.length > 0) {
      try {
        await pauseListings.mutateAsync(pausableListings);
      } catch {
        notify({
          tone: "error",
          title: "Não foi possível pausar os anúncios",
          description:
            "O produto não foi excluído. Tente novamente ou desmarque a opção de pausar.",
        });
        return;
      }
    }

    try {
      await deleteProduct.mutateAsync(pendingDeletion);
      notify({
        tone: "success",
        title: "Produto removido",
        description: pendingDeletion.title,
      });
      cancelDelete();
    } catch {
      notify({ tone: "error", title: "Não foi possível remover o produto" });
    }
  };

  const columns: Column<ProductView>[] = [
    {
      key: "sku",
      header: "SKU",
      render: (row) => (
        <span className="font-mono text-xs font-semibold text-slate-800">
          {row.sku}
        </span>
      ),
    },
    {
      key: "title",
      header: "Título",
      render: (row) => (
        <Link
          to={paths.productDetail(row.id)}
          className="font-medium text-brand-700 hover:underline"
        >
          {row.title}
        </Link>
      ),
    },
    {
      key: "price",
      header: "Preço",
      align: "right",
      render: (row) => formatCurrency(row.price),
    },
    {
      key: "updated",
      header: "Atualizado",
      render: (row) => (
        <span className="text-slate-500">{formatDateTime(row.updatedAt)}</span>
      ),
    },
    {
      key: "actions",
      header: "Ações",
      align: "right",
      render: (row) => (
        <div className="flex items-center justify-end gap-1">
          <Link
            to={paths.productEdit(row.id)}
            aria-label={`Editar ${row.title}`}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-700"
          >
            <Pencil aria-hidden="true" className="h-4 w-4" />
          </Link>
          <button
            type="button"
            onClick={() => {
              setPauseOnDelete(true);
              setPendingDeletion(row);
            }}
            aria-label={`Apagar ${row.title}`}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
          >
            <Trash2 aria-hidden="true" className="h-4 w-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="space-y-6">
        <PageHeader title="Produtos" />

        <Card className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1">
              <label
                htmlFor="product-search"
                className="mb-1.5 block text-sm font-medium text-slate-700"
              >
                Buscar SKU ou titulo
              </label>
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400"
                />
                <input
                  id="product-search"
                  type="search"
                  value={term}
                  placeholder="Buscar SKU ou titulo"
                  onChange={(event) => setTerm(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      setAppliedTerm(term.trim());
                    }
                  }}
                  className="w-full rounded-xl border border-line bg-surface py-2 pr-3 pl-9 text-sm placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none"
                />
              </div>
            </div>

            <Button
              variant="secondary"
              onClick={() => setAppliedTerm(term.trim())}
              disabled={isPending}
            >
              <Search aria-hidden="true" className="h-4 w-4" />
              Buscar
            </Button>

            <div className="flex items-center gap-1 rounded-xl border border-line p-1">
              <button
                type="button"
                onClick={() => setViewMode("table")}
                aria-label="Ver como tabela"
                aria-pressed={viewMode === "table"}
                className={
                  viewMode === "table"
                    ? "rounded-lg bg-slate-100 p-2 text-slate-800"
                    : "rounded-lg p-2 text-slate-400 hover:text-slate-700"
                }
              >
                <Rows3 aria-hidden="true" className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode("grid")}
                aria-label="Ver como grade"
                aria-pressed={viewMode === "grid"}
                className={
                  viewMode === "grid"
                    ? "rounded-lg bg-slate-100 p-2 text-slate-800"
                    : "rounded-lg p-2 text-slate-400 hover:text-slate-700"
                }
              >
                <LayoutGrid aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>

            <Link
              to={paths.productNew}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-brand-800"
            >
              Novo
            </Link>
          </div>
        </Card>

        <Card>
          {isPending && <LoadingBlock label="Carregando produtos..." />}

          {error && (
            <EmptyState
              title="Não foi possível carregar os produtos"
              description="Tente novamente em instantes."
            />
          )}

          {!isPending && !error && filtered.length === 0 && (
            <EmptyState
              icon={<Search aria-hidden="true" className="h-5 w-5" />}
              title={
                appliedTerm.trim().length > 0
                  ? "Nenhum produto encontrado"
                  : "Nenhum produto cadastrado"
              }
              description={
                appliedTerm.trim().length > 0
                  ? "Ajuste a busca por SKU ou título."
                  : "Cadastre o primeiro produto do seu catálogo."
              }
              action={
                appliedTerm.trim().length === 0 ? (
                  <Link
                    to={paths.productNew}
                    className="text-sm font-semibold text-brand-700 hover:underline"
                  >
                    Criar produto
                  </Link>
                ) : null
              }
            />
          )}

          {!isPending && !error && filtered.length > 0 && viewMode === "table" && (
            <Table
              columns={columns}
              rows={filtered}
              rowKey={(row) => row.id}
              caption="Lista de produtos cadastrados"
            />
          )}

          {!isPending && !error && filtered.length > 0 && viewMode === "grid" && (
            <ul className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((product) => (
                <li key={product.id}>
                  <Link
                    to={paths.productDetail(product.id)}
                    className="block rounded-xl border border-line p-4 transition-colors hover:border-brand-300"
                  >
                    <div className="flex items-center gap-3">
                      <Avatar label={product.title} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {product.title}
                        </p>
                        <p className="truncate font-mono text-xs text-slate-500">
                          {product.sku}
                        </p>
                      </div>
                    </div>
                    <p className="mt-3 text-lg font-bold text-slate-900">
                      {formatCurrency(product.price)}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Fab
        label="Criar produto"
        onClick={() => navigate(paths.productNew)}
      />

      <ConfirmDialog
        open={pendingDeletion !== null}
        title="Apagar produto"
        description={deletionDescription}
        confirmLabel={pauseListings.isPending ? "Pausando..." : "Apagar"}
        confirmDisabled={isDeleting || listingsPending}
        onCancel={cancelDelete}
        onConfirm={confirmDelete}
      >
        {pausableListings.length > 0 && (
          <label className="flex items-start gap-2 rounded-lg border border-line bg-slate-50/60 p-3 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={pauseOnDelete}
              onChange={(event) => setPauseOnDelete(event.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-line text-brand-700"
            />
            <span>
              Pausar/Encerrar os anúncios no Mercado Livre ao excluir o
              produto
            </span>
          </label>
        )}
      </ConfirmDialog>
    </>
  );
}