import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  catalogClient,
  type PlatformMapping,
  type PlatformMappingCreate,
} from "../../lib/api/catalog-client";
import { integrationsClient } from "../../lib/api/integrations-client";
import {
  mercadolibreClient,
  type CreateMlItemRequest,
  type UpdateMlItemRequest,
} from "../../lib/api/mercadolibre-client";
import { queryKeys } from "../products/queries";

export const localMarketplaceItemsKey = ["ml-local-items"] as const;

/** Campos mínimos para pausar um anúncio no Mercado Livre. */
export type PausableListing = Pick<
  PlatformMapping,
  "platform" | "platform_product_id" | "is_active"
>;

/** Atributos técnicos de uma categoria (cache de 24h). */
export function useCategoryAttributes(categoryId: string) {
  return useQuery({
    queryKey: ["category-attributes", categoryId],
    queryFn: async () => mercadolibreClient.getCategoryAttributes(categoryId),
    enabled: !!categoryId,
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
  });
}



/** Categorias raiz do site (fallback de navegação em árvore). */
export function useSiteCategories() {
  return useQuery({
    queryKey: ["ml-site-categories"],
    queryFn: () => mercadolibreClient.listSiteCategories(),
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
  });
}

/** Detalhe de uma categoria, incluindo filhas (fallback de navegação em árvore). */
export function useCategoryDetail(categoryId: string | undefined) {
  return useQuery({
    queryKey: ["ml-category-detail", categoryId],
    queryFn: async () => mercadolibreClient.getCategory(categoryId!),
    enabled: !!categoryId,
    staleTime: 24 * 60 * 60 * 1000, // 24 hours
  });
}

/** Detalhe de um item publicado no Mercado Livre (pré-edição). */
export function useMlItem(itemId: string | undefined) {
  return useQuery({
    queryKey: ["ml-item", itemId],
    queryFn: async () => mercadolibreClient.getMlItem(itemId!),
    enabled: !!itemId,
  });
}

/** Cria o anúncio no Mercado Livre e registra o vínculo local. */
export function useCreateMlItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateMlItemRequest) =>
      mercadolibreClient.createMlItem(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}

/** Atualiza um anúncio existente no Mercado Livre. */
export function useUpdateMlItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: {
      itemId: string;
      payload: UpdateMlItemRequest;
    }) => mercadolibreClient.updateMlItem(input.itemId, input.payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
    },
  });
}

/**
 * Pausa anúncios ativos no Mercado Livre.
 *
 * Usado antes de arquivar um produto (opção do modal) e pela ação rápida da
 * lista de anúncios. Rejeita a operação inteira se qualquer pausa falhar, para
 * que o chamador possa abortar a exclusão e evitar anúncios órfãos ativos.
 */
export function usePauseMlListings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (listings: PausableListing[]) => {
      const targets = listings.filter(
        (listing) =>
          listing.platform === "mercado_livre" &&
          listing.is_active &&
          Boolean(listing.platform_product_id)
      );

      await Promise.all(
        targets.map((listing) =>
          mercadolibreClient.updateMlItem(listing.platform_product_id!, {
            status: "paused",
          })
        )
      );

      return targets.length;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
      void queryClient.invalidateQueries({
        queryKey: localMarketplaceItemsKey,
      });
    },
  });
}

/** Cria/substituí a descrição de um item (POST /items/{id}/description, v3). */
export function useCreateMlItemDescription() {
  return useMutation({
    mutationFn: (input: {
      itemId: string;
      plainText: string;
    }) => mercadolibreClient.createMlItemDescription(input.itemId, input.plainText),
  });
}

/** Vínculos locais de anúncios (produto ↔ marketplace). */
export function usePlatformMappings() {
  return useQuery({
    queryKey: queryKeys.listings,
    queryFn: () => catalogClient.listPlatformMappings(),
  });
}

/** Anúncios importados/sincronizados no integrations-service. */
export function useLocalMarketplaceItems() {
  return useQuery({
    queryKey: localMarketplaceItemsKey,
    queryFn: () => integrationsClient.listLocalMercadoLivreItems(),
  });
}

/** Registra o vínculo local de um anúncio já publicado. */
export function useCreatePlatformMapping() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PlatformMappingCreate) =>
      catalogClient.createPlatformMapping(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}

/** Remove um vínculo local de anúncio. */
export function useDeletePlatformMapping() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => catalogClient.deletePlatformMapping(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
    },
  });
}

/** Mantido para compatibilidade com telas antigas (dashboard, busca global). */
export const useAllListings = usePlatformMappings;
