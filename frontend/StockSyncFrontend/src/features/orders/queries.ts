import { useQuery } from "@tanstack/react-query";
import { api } from "../../mock/handlers";

export const orderQueryKeys = {
  orders: ["orders"] as const,
} as const;

export function useOrders() {
  return useQuery({
    queryKey: orderQueryKeys.orders,
    queryFn: () => api.orders.list(),
  });
}