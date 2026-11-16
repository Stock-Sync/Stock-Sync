import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  catalogClient,
  type ProductActiveListing,
  type SKUCreate,
} from "../../lib/api/catalog-client";
import { mercadolibreClient } from "../../lib/api/mercadolibre-client";
import type { ProductView } from "../../types/view-models";
import { toProductView } from "../../types/view-models";

/**
 * Chaves de cache do React Query.
 *
 * Centralizadas para que uma invalidação feita em uma feature não quebre a
 * outra. `products` é a raiz: produto, anúncio e dashboard derivam dela.
 */
export const queryKeys = {
  products: ["products"] as const,
  product: (id: number) => ["products", id] as const,
  listings: ["listings"] as const,
  stores: ["stores"] as const,
  orders: ["orders"] as const,
  notifications: ["notifications"] as const,
} as const;

/**
 * `orders` fica com as demais chaves por ser um recurso derivado do mesmo
 * conjunto de dados do dashboard; a query vive em `features/orders`.
 */

/** Produtos já achatados na visão das telas. */
export function useProductViews() {
  const query = useQuery({
    queryKey: queryKeys.products,
    // Stock deducted by marketplace sales flows through Redis Streams into
    // the catalog; refetch on focus/interval so the list reflects it without
    // a manual reload.
    refetchOnWindowFocus: true,
    refetchInterval: 30_000,
    queryFn: async () => {
      const [products, skus] = await Promise.all([
        catalogClient.listProducts(),
        catalogClient.listSkus(),
      ]);

      const skuByProduct = new Map(skus.map((sku) => [sku.product_id, sku]));
      return products.flatMap((product) => {
        const sku = skuByProduct.get(product.id);
        return sku ? [toProductView(product, sku)] : [];
      });
    },
  });

  const views = useMemo(() => query.data ?? [], [query.data]);
  return { ...query, products: views };
}

export function useProductView(id: number) {
  const { products, isPending, isError, error } = useProductViews();
  const product = useMemo(
    () => products.find((item) => item.id === id),
    [products, id]
  );

  return { product, isPending, isError, error };
}

/** Anúncios ativos vinculados a um SKU (usado no diálogo de exclusão). */
export function useProductListings(skuId: number | undefined) {
  return useQuery({
    queryKey: [...queryKeys.listings, "sku", skuId] as const,
    enabled: skuId !== undefined,
    queryFn: async () => {
      const mappings = await catalogClient.listPlatformMappings();
      return mappings.filter(
        (mapping) => mapping.sku_id === skuId && mapping.is_active
      );
    },
  });
}

/**
 * Cria produto + SKU atomicamente via composite endpoint (Plan 11).
 */
export function useCreateProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      sku: string;
      title: string;
      description: string;
      price: number;
      stockQuantity: number;
      pictures: { source: string }[];
    }) => {
      const composite = await catalogClient.createProductComposite({
        name: input.title,
        description: input.description,
        internal_sku: input.sku,
        price: input.price,
        stock_quantity: input.stockQuantity,
        pictures: input.pictures.map((p) => p.source),
      });
      return toProductView(composite, composite.sku);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}

/**
 * Atualiza produto + SKU atomicamente via composite endpoint (Plan 11).
 */
export function useUpdateProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: {
      id: number;
      skuId: number;
      sku: string;
      title: string;
      description: string;
      price: number;
      stockQuantity: number;
      pictures: { source: string }[];
    }) => {
      const composite = await catalogClient.updateProductComposite(input.id, {
        name: input.title,
        description: input.description,
        internal_sku: input.sku,
        price: input.price,
        stock_quantity: input.stockQuantity,
        pictures: input.pictures.map((p) => p.source),
      });
      return toProductView(composite, composite.sku);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}

/**
 * Arquiva o produto e seus SKUs.
 *
 * O backend faz o soft delete do produto, dos SKUs e desativa os vínculos
 * em uma única operação; não é necessário chamar `deleteSku` depois.
 */
export function useDeleteProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (product: ProductView) => {
      await catalogClient.deleteProduct(product.productId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
      void queryClient.invalidateQueries({ queryKey: ["listings"] });
      void queryClient.invalidateQueries({ queryKey: ["ml-local-items"] });
    },
  });
}

/**
 * Pausa e zera um conjunto de anúncios no Mercado Livre (Plan 10).
 *
 * A operação é sequencial: se um anúncio falhar, as chamadas seguintes são
 * abortadas para que o usuário possa tentar novamente sem continuar mexendo
 * em um estado parcial. Anúncios já encerrados são ignorados.
 */
export function usePauseAndZeroListings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (listings: ProductActiveListing[]) => {
      let updated = 0;
      for (const listing of listings) {
        if (!listing.id || listing.status === "closed") {
          continue;
        }
        // A paused listing only needs its quantity zeroed; an active one must
        // also transition to paused.
        await mercadolibreClient.updateMlItem(
          listing.id,
          listing.status === "paused"
            ? { available_quantity: 0 }
            : { status: "paused", available_quantity: 0 }
        );
        updated += 1;
      }
      return updated;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
      void queryClient.invalidateQueries({ queryKey: ["listings"] });
      void queryClient.invalidateQueries({ queryKey: ["ml-local-items"] });
    },
  });
}

/** Desvincula todos os anúncios locais do produto (Plan 10). */
export function useUnbindProductListings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (productId: number) =>
      catalogClient.unbindProductListings(productId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
      void queryClient.invalidateQueries({ queryKey: ["listings"] });
      void queryClient.invalidateQueries({ queryKey: ["ml-local-items"] });
    },
  });
}
