import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { syncClient } from "../../lib/api/sync-client";
import { localMarketplaceItemsKey } from "../listings/queries";
import { queryKeys } from "../products/queries";

interface Notification {
  id: number;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export function useNotifications() {
  return useQuery<Notification[]>({
    queryKey: queryKeys.notifications,
    queryFn: async () => {
      // Notifications not implemented in backend yet
      return [];
    },
  });
}

export function useMarkNotificationsAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      // Notifications not implemented in backend yet
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.notifications,
      });
    },
  });
}

/**
 * "Sincronizar Tudo" do dashboard e "Sincronizar" dos anúncios.
 *
 * Chama o sync-service (POST /api/v1/sync/listings/pull), que importa todos
 * os anúncios do Mercado Livre para a base local e cria os vínculos que
 * faltam. Retorna o resumo do pull para o toast.
 */
export function useRunSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => syncClient.pullListings(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
      void queryClient.invalidateQueries({ queryKey: localMarketplaceItemsKey });
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
      void queryClient.invalidateQueries({ queryKey: queryKeys.orders });
    },
  });
}
