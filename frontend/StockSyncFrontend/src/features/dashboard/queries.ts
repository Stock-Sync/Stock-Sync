import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../mock/handlers";
import { queryKeys } from "../products/queries";

export function useOrders() {
  return useQuery({
    queryKey: queryKeys.orders,
    queryFn: () => api.orders.list(),
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: queryKeys.notifications,
    queryFn: () => api.notifications.list(),
  });
}

export function useMarkNotificationsAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.notifications.markAllAsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.notifications,
      });
    },
  });
}

/**
 * "Sincronizar Tudo" do dashboard.
 *
 * Hoje roda contra o mock; quando o sync-service expor o endpoint, substitua
 * apenas `api.sync.runAll()` pela chamada HTTP.
 */
export function useRunSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.sync.runAll(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}