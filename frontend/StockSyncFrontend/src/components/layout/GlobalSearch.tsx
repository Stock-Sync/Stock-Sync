import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Megaphone, Package, Search, Store } from "lucide-react";
import { PLATFORM_LABELS } from "../../types/catalog";
import { formatCurrency } from "../../lib/format";
import { paths } from "../../routes/paths";
import { useDisclosure, useDismissOnOutside } from "../../hooks/use-disclosure";
import {
  useAllListings,
  useProductViews,
} from "../../features/products/queries";
import { useStores } from "../../features/stores/queries";
import { cn } from "../../lib/cn";
import { Badge } from "../ui/Badge";

interface SearchResult {
  id: string;
  group: string;
  title: string;
  subtitle: string;
  to: string;
  icon: typeof Package;
}

/**
 * Busca global do topo (produtos, lojas e anúncios).
 *
 * Filtra client-side sobre os dados já carregados pelo React Query — não há
 * endpoint de busca no backend. Quando existir, trocar `results` por uma query
 * dedicada; a UI não precisa mudar.
 */
export function GlobalSearch() {
  const [term, setTerm] = useState("");
  const { isOpen, close, open } = useDisclosure();
  const containerRef = useDismissOnOutside(isOpen, close);

  const { products } = useProductViews();
  const { data: listings = [] } = useAllListings();
  const { data: stores = [] } = useStores();

  const results = useMemo<SearchResult[]>(() => {
    const needle = term.trim().toLowerCase();
    if (needle.length === 0) {
      return [];
    }

    const productResults: SearchResult[] = products
      .filter(
        (product) =>
          product.sku.toLowerCase().includes(needle) ||
          product.title.toLowerCase().includes(needle)
      )
      .map((product) => ({
        id: `product-${product.id}`,
        group: "Produtos",
        title: product.title,
        subtitle: `${product.sku} · ${formatCurrency(product.price)}`,
        to: paths.productDetail(product.id),
        icon: Package,
      }));

    const listingResults: SearchResult[] = listings
      .filter(
        (listing) =>
          listing.platform_sku.toLowerCase().includes(needle) ||
          PLATFORM_LABELS[listing.platform].toLowerCase().includes(needle)
      )
      .map((listing) => ({
        id: `listing-${listing.id}`,
        group: "Anúncios",
        title: listing.platform_sku,
        subtitle: PLATFORM_LABELS[listing.platform],
        to: paths.listings,
        icon: Megaphone,
      }));

    const storeResults: SearchResult[] = stores
      .filter(
        (store) =>
          store.name.toLowerCase().includes(needle) ||
          store.external_id.toLowerCase().includes(needle)
      )
      .map((store) => ({
        id: `store-${store.id}`,
        group: "Lojas",
        title: store.name,
        subtitle: `${store.marketplace} · ${store.external_id}`,
        to: paths.stores,
        icon: Store,
      }));

    return [...productResults, ...listingResults, ...storeResults].slice(0, 8);
  }, [term, products, listings, stores]);

  return (
    <div ref={containerRef} className="relative w-full max-w-md">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (results.length > 0) {
            close();
          }
        }}
      >
        <label htmlFor="global-search" className="sr-only">
          Buscar produtos, lojas ou anúncios
        </label>
        <div className="relative">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400"
          />
          <input
            id="global-search"
            type="search"
            value={term}
            placeholder="Buscar produtos, lojas, anúncios..."
            onChange={(event) => {
              setTerm(event.target.value);
              open();
            }}
            onFocus={open}
            className="w-full rounded-xl border border-line bg-slate-50 py-2 pr-3 pl-9 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-surface focus:ring-2 focus:ring-brand-500/20 focus:outline-none"
          />
        </div>
      </form>

      {isOpen && term.trim().length > 0 && (
        <div className="absolute left-0 z-40 mt-2 w-full overflow-hidden rounded-xl border border-line bg-surface shadow-pop">
          {results.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-500">
              Nenhum resultado para "{term.trim()}".
            </p>
          ) : (
            <ul className="max-h-80 overflow-y-auto py-1">
              {results.map((result) => {
                const Icon = result.icon;
                return (
                  <li key={result.id}>
                    <Link
                      to={result.to}
                      onClick={() => {
                        setTerm("");
                        close();
                      }}
                      className="flex items-center gap-3 px-4 py-2 transition-colors hover:bg-slate-50"
                    >
                      <span
                        className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                          "bg-brand-50 text-brand-700"
                        )}
                      >
                        <Icon aria-hidden="true" className="h-4 w-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-slate-800">
                          {result.title}
                        </span>
                        <span className="block truncate text-xs text-slate-500">
                          {result.subtitle}
                        </span>
                      </span>
                      <Badge tone="neutral">{result.group}</Badge>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}