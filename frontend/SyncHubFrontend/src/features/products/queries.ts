import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { catalogClient, type SKUCreate } from "../../lib/api/catalog-client";
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
 * Cria produto + SKU em uma única mutação.
 *
 * O backend exige dois POSTs (`/products` e `/skus`), então o fluxo de criação
 * é orquestrado aqui para que a tela trate como uma única operação.
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
      const product = await catalogClient.createProduct({
        name: input.title,
        description: input.description,
        pictures: input.pictures.map((p) => p.source),
      });
      const skuPayload: SKUCreate = {
        product_id: product.id,
        internal_sku: input.sku,
        price: input.price,
        stock_quantity: input.stockQuantity,
      };
      const sku = await catalogClient.createSku(skuPayload);
      return toProductView(product, sku);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}

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
      const product = await catalogClient.updateProduct(input.id, {
        name: input.title,
        description: input.description,
        pictures: input.pictures.map((p) => p.source),
      });
      const sku = await catalogClient.updateSku(input.skuId, {
        internal_sku: input.sku,
        price: input.price,
        stock_quantity: input.stockQuantity,
      });
      return toProductView(product, sku);
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
    },
  });
}

