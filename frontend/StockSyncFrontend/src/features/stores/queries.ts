import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../mock/handlers";
import type { Store, StoreCreate } from "../../types/entities";

export const storeQueryKeys = {
  stores: ["stores"] as const,
} as const;

export function useStores() {
  return useQuery({
    queryKey: storeQueryKeys.stores,
    queryFn: () => api.stores.list(),
  });
}

export function useCreateStore() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: StoreCreate) => api.stores.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: storeQueryKeys.stores,
      });
    },
  });
}

export function useDeleteStore() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (store: Store) => api.stores.remove(store.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: storeQueryKeys.stores,
      });
    },
  });
}