import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { storesClient, type Store, type StoreCreate } from "../../lib/api/stores-client";

export const storeQueryKeys = {
  stores: ["stores"] as const,
} as const;

export function useStores() {
  return useQuery({
    queryKey: storeQueryKeys.stores,
    queryFn: () => storesClient.list(),
  });
}

export function useCreateStore() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: StoreCreate) => storesClient.create(payload),
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
    mutationFn: (store: Store) => storesClient.remove(store.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: storeQueryKeys.stores,
      });
    },
  });
}