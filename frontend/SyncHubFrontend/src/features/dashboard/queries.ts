import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { salesClient } from "../../lib/api/sales-client";
import { queryKeys } from "../products/queries";

export function useOrders() {
  return useQuery({
    queryKey: queryKeys.orders,
    queryFn: () => salesClient.listOrders(),
  });
}

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
 * "Sincronizar Tudo" do dashboard.
 *
 * Hoje roda contra o mock; quando o sync-service expor o endpoint, substitua
 * apenas pela chamada HTTP.
 */
export function useRunSync() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      // Sync service not implemented yet
      return 0;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.listings });
      void queryClient.invalidateQueries({ queryKey: queryKeys.products });
    },
  });
}